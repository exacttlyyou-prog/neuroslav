"""
Фоновый парсер для страницы "встречи 2026".
Периодически проверяет последний блок на странице через MCP Notion и копирует его содержимое.
"""
import asyncio
import hashlib
from typing import Optional, Dict, Any
from loguru import logger
from datetime import datetime

from app.config import get_settings
from app.services.notion_mcp_service import NotionMCPService


class NotionBackgroundParser:
    """Фоновый парсер для страницы встреч Notion."""
    
    def __init__(self):
        self.settings = get_settings()
        self.mcp_service: Optional[NotionMCPService] = None
        self.page_id = self.settings.notion_meeting_page_id
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
            logger.warning("⚠️ NOTION_MEETING_PAGE_ID не установлен, фоновый парсер не запущен")
            return
        
        try:
            self.mcp_service = NotionMCPService()
            # Проверяем, что MCP сервер может запуститься
            if not await self.mcp_service.start_server():
                logger.warning("⚠️ Не удалось запустить MCP сервер, фоновый парсер не запущен")
                logger.warning("💡 Убедитесь, что установлен Node.js и npx доступен")
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
        
        while self.running:
            try:
                await self._check_and_copy_last_block()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("Фоновый парсер получил сигнал остановки")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле фонового парсера: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_and_copy_last_block(self):
        """Проверяет последний блок на странице через MCP и копирует его, если он новый."""
        if not self.page_id or not self.mcp_service:
            return
        
        try:
            # Получаем контент страницы через MCP
            logger.debug("🔍 Проверяю последний блок через MCP Notion...")
            
            # Проверяем, что MCP сервер запущен
            if not await self.mcp_service.start_server():
                logger.warning("⚠️ MCP сервер не запущен, пропускаем проверку")
                return
            
            result = await self.mcp_service.fetch_page(self.page_id)
            
            if not result:
                logger.debug("Не удалось получить данные страницы через MCP")
                return
            
            # Извлекаем контент из результата MCP
            mcp_content = self.mcp_service._extract_content_from_mcp_result(result)
            
            if not mcp_content or len(mcp_content.strip()) < 10:
                logger.debug("Контент страницы пустой или слишком короткий")
                return
            
            # Парсим последнюю встречу из meeting-notes блоков
            meeting_data = self.mcp_service.extract_last_meeting_from_mcp_content(mcp_content)
            
            if not meeting_data:
                logger.debug("Не найдено meeting-notes блоков на странице")
                return
            
            content = meeting_data.get("content", "").strip()
            meeting_type = meeting_data.get("type", "unknown")
            
            # Если блок пустой, ничего не копируем
            if not content or len(content) < 10:
                logger.debug(f"Контент встречи ({meeting_type}) пустой или слишком короткий, пропускаем")
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
                
                # Отправляем минутки в Telegram админу и всем участникам
                try:
                    send_result = await telegram.send_meeting_minutes(
                        summary=process_result.get("summary", ""),
                        action_items=process_result.get("action_items", []),
                        participants=process_result.get("participants", []),
                        send_to_admin=bool(self.settings.admin_chat_id),
                        send_to_participants=True
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
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка при отправке минуток в Telegram: {e}", exc_info=True)
                
            except Exception as e:
                logger.error(f"❌ Ошибка при автоматической обработке встречи: {e}", exc_info=True)
            
        except Exception as e:
            logger.error(f"Ошибка при проверке последнего блока: {e}", exc_info=True)
    
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
