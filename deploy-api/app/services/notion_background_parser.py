"""
Фоновый парсер для страницы "встречи 2026".
Периодически проверяет последний блок на странице через MCP Notion и копирует его содержимое.
"""
import asyncio
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from loguru import logger
from datetime import datetime

from app.config import get_settings
from app.services.notion_mcp_service import NotionMCPService
from app.services.notion_service import NotionService


class NotionBackgroundParser:
    """Фоновый парсер для страницы встреч Notion."""
    
    def __init__(self):
        self.settings = get_settings()
        self.mcp_service: Optional[NotionMCPService] = None
        self.notion_service: Optional[NotionService] = None
        # Корень контекста: AI Context или meeting_page
        self.page_id = getattr(self.settings, "notion_ai_context_page_id", None) or self.settings.notion_meeting_page_id
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.last_content_hash: Optional[str] = None
        self.last_check_time: Optional[datetime] = None
        self.check_interval = 60  # Проверка каждые 60 секунд
    
    async def start(self):
        """Запускает фоновый парсер."""
        if self.running:
            logger.warning("Фоновый парсер уже запущен")
            return
        
        if not self.page_id:
            logger.warning("⚠️ NOTION_AI_CONTEXT_PAGE_ID / NOTION_MEETING_PAGE_ID не установлены, фоновый парсер не запущен")
            return
        
        try:
            self.mcp_service = NotionMCPService()
            self.notion_service = NotionService()
            
            # Проверяем, что MCP сервер может запуститься
            mcp_started = await self.mcp_service.start_server()
            if not mcp_started:
                logger.warning("⚠️ Не удалось запустить MCP сервер, будем использовать Notion API напрямую")
            
            # Проверяем Notion API
            if not await self.notion_service.validate_token():
                logger.error("❌ Notion API недоступен, фоновый парсер не может работать")
                return

            self.running = True
            self.task = asyncio.create_task(self._run_loop())
            logger.info(f"✅ Фоновый парсер запущен для страницы: {self.page_id}")
        except ValueError as e:
            # NOTION_TOKEN не установлен
            logger.warning(f"⚠️ {e}, фоновый парсер не запущен")
            self.running = False
        except Exception as e:
            logger.error(f"❌ Ошибка запуска фонового парсера: {e}", exc_info=True)
            self.running = False
    
    async def stop(self):
        """Останавливает фоновый парсер."""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        # Останавливаем MCP сервер, если он был запущен
        if self.mcp_service:
            try:
                await self.mcp_service.stop_server()
            except Exception as e:
                logger.debug(f"Ошибка при остановке MCP сервера: {e}")
        
        logger.info("Фоновый парсер остановлен")
    
    async def _run_loop(self):
        """Основной цикл фонового парсера."""
        logger.info(f"🔄 Фоновый парсер начал работу (интервал: {self.check_interval} сек)")
        
        # Счетчик для периодической индексации (каждые 10 проверок = ~10 минут)
        check_counter = 0
        
        while self.running:
            try:
                await self._check_and_copy_last_block()
                
                # Периодически запускаем автоматическую индексацию страниц
                check_counter += 1
                if check_counter >= 10:  # Каждые 10 проверок (~10 минут)
                    check_counter = 0
                    try:
                        await self.auto_index_new_pages()
                    except Exception as e:
                        logger.warning(f"Ошибка при автоматической индексации: {e}")
                
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("Фоновый парсер получил сигнал остановки")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле фонового парсера: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_and_copy_last_block(self):
        """Проверяет последний блок на странице через MCP и копирует его, если он новый."""
        if not self.page_id:
            return
        
        # Проверяем, идет ли запись встречи (чтобы не обрабатывать чанки как отдельные встречи)
        recording_flag_path = Path("/tmp/is_recording.flag")
        if recording_flag_path.exists():
            logger.debug("⏸ Запись идет, пропускаем обработку блоков (чтобы не обрабатывать чанки как встречи)")
            return
        
        content = ""
        meeting_type = "unknown"
        mcp_success = False
        
        try:
            # 1. Пробуем через MCP (если он инициализирован)
            if self.mcp_service:
                logger.debug("🔍 Проверяю последний блок через MCP Notion...")
                
                # Проверяем, что MCP сервер запущен
                if await self.mcp_service.start_server():
                    result = await self.mcp_service.fetch_page(self.page_id)
                    
                    if result:
                        # Извлекаем контент из результата MCP
                        mcp_content = self.mcp_service._extract_content_from_mcp_result(result)
                        
                        if mcp_content and len(mcp_content.strip()) >= 10:
                            # Парсим последнюю встречу из meeting-notes блоков
                            meeting_data = self.mcp_service.extract_last_meeting_from_mcp_content(mcp_content)
                            
                            if meeting_data:
                                content = meeting_data.get("content", "").strip()
                                meeting_type = meeting_data.get("type", "unknown")
                                mcp_success = True
                            else:
                                logger.debug("Не найдено meeting-notes блоков на странице (MCP)")
                        else:
                            logger.debug("Контент страницы пустой или слишком короткий (MCP)")
                    else:
                        logger.debug("Не удалось получить данные страницы через MCP")
                else:
                    logger.debug("MCP сервер не запущен, пропускаем проверку через MCP")
            
            # 2. Если MCP не сработал, пробуем через Notion API
            if not mcp_success and self.notion_service:
                logger.debug("🔍 Проверяю последний блок через Notion API...")
                try:
                    last_block = await self.notion_service.get_last_meeting_block(self.page_id)
                    block_content = last_block.get("content", "").strip()
                    
                    if block_content and len(block_content) >= 10:
                        content = block_content
                        meeting_type = "api_block"
                        logger.debug(f"Получен контент через API (ID: {last_block.get('block_id')})")
                    else:
                        logger.debug("Последний блок пустой или слишком короткий (API)")
                except Exception as e:
                    logger.error(f"Ошибка получения последнего блока через API: {e}")
            
            # Если ничего не нашли, выходим
            if not content or len(content) < 10:
                return
            
            # ПРОВЕРКА 1: Пропускаем блоки, которые содержат только маркеры чанков без саммари
            if "[Чанк #" in content and "📋 Саммари встречи" not in content and "Саммари встречи" not in content:
                logger.debug("Блок содержит только чанки без саммари, пропускаем обработку")
                return
            
            # ПРОВЕРКА 2: Пропускаем, если это промежуточный чанк (начинается с маркера чанка)
            if content.strip().startswith("[Чанк #"):
                logger.debug("Это промежуточный чанк, пропускаем обработку")
                return
            
            # ПРОВЕРКА 3: Пропускаем, если нет маркера завершения и нет саммари (встреча не завершена)
            has_completion_marker = "[MEETING_COMPLETE]" in content or "[ФИНАЛЬНАЯ ОБРАБОТКА]" in content
            has_summary = "📋 Саммари встречи" in content or "Саммари встречи" in content
            if not has_completion_marker and not has_summary:
                logger.debug("Встреча не завершена (нет саммари и маркера завершения), пропускаем обработку")
                return
            
            # Используем хеш контента как идентификатор блока
            content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
            
            # Проверяем, новый ли это блок
            if content_hash == self.last_content_hash:
                logger.debug(f"Блок с хешем {content_hash} уже обработан ранее, пропускаем")
                return
            
            # Новый блок - обрабатываем его
            logger.info(f"📋 Найден новый блок: {content_hash} ({len(content)} символов, тип: {meeting_type})")
            logger.info(f"Содержимое блока (первые 200 символов): {content[:200]}...")
            
            # Сохраняем хеш последнего обработанного блока
            self.last_content_hash = content_hash
            self.last_check_time = datetime.now()
            
            # Автоматически обрабатываем найденный блок через MeetingWorkflow
            logger.info(f"🤖 Запуск автоматической обработки встречи из блока {content_hash}...")
            try:
                from app.workflows.meeting_workflow import MeetingWorkflow
                from app.services.telegram_service import TelegramService
                
                workflow = MeetingWorkflow()
                telegram = TelegramService()
                
                # Обрабатываем встречу с контентом из блока
                process_result = await workflow.process_meeting(
                    transcript=content,
                    notion_page_id=self.page_id
                )
                
                meeting_id = process_result.get("meeting_id")
                participants_count = len(process_result.get("participants", []))
                projects_count = len(process_result.get("projects", []))
                action_items_count = len(process_result.get("action_items", []))
                
                logger.info(
                    f"✅ Встреча обработана: {meeting_id}\n"
                    f"   Участники: {participants_count}, Проекты: {projects_count}, Задачи: {action_items_count}"
                )
                
                # Логируем предупреждения, если есть
                warnings = process_result.get("verification_warnings", [])
                if warnings:
                    logger.warning(f"⚠️ Предупреждения при обработке встречи:\n" + "\n".join(warnings))
                
                # Извлекаем теги из встречи
                tags = []
                try:
                    tags = workflow.extract_tags(
                        transcript=content,
                        projects=process_result.get("projects", []),
                        action_items=process_result.get("action_items", []),
                        participants=process_result.get("participants", [])
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось извлечь теги: {e}")
                
                # Формируем дату встречи
                from datetime import datetime
                meeting_date = datetime.now().strftime('%Y-%m-%d %H:%M')
                
                # Формируем ссылку на AI Context (если есть)
                ai_context_link = None
                try:
                    from app.services.notion_service import NotionService
                    notion = NotionService()
                    ai_context_page_id = await notion.get_or_create_ai_context_page(self.page_id)
                    # Формируем ссылку в формате URL для Notion API
                    # Передаем page_id напрямую, save_meeting_minutes сам создаст правильную ссылку
                    ai_context_link = ai_context_page_id
                except Exception as e:
                    logger.debug(f"Не удалось создать ссылку на AI Context: {e}")
                
                # Отправляем минутки в Telegram админу и всем участникам
                # (сохранение в Notion происходит автоматически внутри send_meeting_minutes)
                try:
                    logger.info("📋 Начинаю отправку минуток в Telegram и сохранение в Notion...")
                    send_result = await telegram.send_meeting_minutes(
                        summary=process_result.get("summary", ""),
                        action_items=process_result.get("action_items", []),
                        participants=process_result.get("participants", []),
                        send_to_admin=bool(self.settings.admin_chat_id),
                        send_to_participants=True,
                        tags=tags,
                        meeting_date=meeting_date,
                        ai_context_link=ai_context_link,
                        key_decisions=process_result.get("key_decisions", []),
                        insights=process_result.get("insights", []),
                        next_steps=process_result.get("next_steps", [])
                    )
                    
                    # Логируем результаты отправки
                    if send_result.get("admin_message_id"):
                        logger.info(f"✅ Минутки встречи отправлены админу: {send_result['admin_message_id']}")
                    
                    participants_sent = send_result.get("participants", [])
                    if participants_sent:
                        sent_count = sum(1 for p in participants_sent if p.get("message_id"))
                        error_count = sum(1 for p in participants_sent if p.get("error"))
                        logger.info(f"✅ Минутки отправлены {sent_count} участникам, ошибок: {error_count}")
                        
                        # Логируем детали для каждого участника
                        for p in participants_sent:
                            if p.get("message_id"):
                                logger.info(f"   ✅ {p['name']}: отправлено (message_id: {p['message_id']})")
                            elif p.get("error"):
                                logger.warning(f"   ⚠️ {p['name']}: {p['error']}")
                    else:
                        logger.info("ℹ️ Нет участников для отправки минуток")
                    
                    logger.info("✅ Процесс отправки минуток завершен")
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка при отправке минуток в Telegram: {e}", exc_info=True)
                    # Пробуем сохранить минутки напрямую в Notion, даже если отправка в Telegram не удалась
                    try:
                        logger.info("🔄 Пробую сохранить минутки напрямую в Notion...")
                        from app.services.notion_service import NotionService
                        notion = NotionService()
                        minutes_id = await notion.save_meeting_minutes(
                            summary=process_result.get("summary", ""),
                            action_items=process_result.get("action_items", []),
                            participants=process_result.get("participants", []),
                            tags=tags,
                            meeting_date=meeting_date,
                            ai_context_link=ai_context_link,
                            key_decisions=process_result.get("key_decisions", []),
                            insights=process_result.get("insights", []),
                            next_steps=process_result.get("next_steps", [])
                        )
                        logger.info(f"✅ Минутки сохранены в Notion напрямую: {minutes_id}")
                    except Exception as notion_error:
                        logger.error(f"❌ Критическая ошибка: не удалось сохранить минутки ни в Telegram, ни в Notion: {notion_error}", exc_info=True)
                
            except Exception as e:
                logger.error(f"❌ Ошибка при автоматической обработке встречи: {e}", exc_info=True)
            
        except Exception as e:
            logger.error(f"Ошибка при проверке последнего блока: {e}", exc_info=True)
    
    async def auto_index_new_pages(self):
        """
        Автоматически индексирует новые страницы из Notion в базу знаний.
        Вызывается периодически для синхронизации.
        """
        try:
            from app.services.rag_service import RAGService
            from app.services.notion_service import NotionService
            
            rag = RAGService()
            notion = NotionService()
            
            # Синхронизируем все дочерние страницы
            results = await rag.sync_with_notion(notion, self.page_id)
            
            if results.get("error"):
                logger.warning(f"Ошибка при автоматической индексации: {results['error']}")
            else:
                logger.info(
                    f"Автоиндексация завершена: "
                    f"индексировано {len(results.get('indexed', []))}, "
                    f"пропущено {len(results.get('skipped', []))}, "
                    f"ошибок {len(results.get('failed', []))}"
                )
            
        except Exception as e:
            logger.error(f"Ошибка при автоматической индексации страниц: {e}")
    
    async def get_last_copied_block(self) -> Optional[Dict[str, Any]]:
        """Возвращает информацию о последнем скопированном блоке."""
        if not self.last_content_hash:
            return None
        
        return {
            "content_hash": self.last_content_hash,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
            "page_id": self.page_id
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Возвращает статус фонового парсера."""
        return {
            "running": self.running,
            "page_id": self.page_id,
            "check_interval": self.check_interval,
            "last_content_hash": self.last_content_hash,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None
        }
