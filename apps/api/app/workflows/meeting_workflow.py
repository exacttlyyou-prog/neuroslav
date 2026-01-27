"""
Workflow обработки встреч.
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
from loguru import logger
import uuid

from app.services.ollama_service import OllamaService
from app.services.notion_service import NotionService
from app.services.rag_service import RAGService
from app.services.context_loader import ContextLoader
from app.services.telegram_service import TelegramService
from app.services.transcription_service import transcription_service
from app.models.schemas import MeetingAnalysis
from app.db.models import Meeting, Contact
from app.db.database import AsyncSessionLocal
from app.config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path
import asyncio
import tempfile
import os


class MeetingWorkflow:
    """Workflow для обработки встреч."""
    
    def __init__(self):
        self.context_loader = ContextLoader()
        self.ollama = OllamaService(context_loader=self.context_loader)
        self.notion = NotionService()
        self.rag = RAGService()
        self.telegram = TelegramService()
    
    async def process_meeting(
        self,
        transcript: Optional[str] = None,
        audio_file: Optional[bytes] = None,
        notion_page_id: Optional[str] = None,
        sender_username: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Обрабатывает встречу: транскрибирует (если аудио), анализирует, извлекает участников, генерирует draft.
        
        Args:
            transcript: Текст транскрипта (если есть)
            audio_file: Аудио файл (если есть, будет транскрибирован)
            notion_page_id: ID страницы Notion (опционально)
            
        Returns:
            Словарь с результатом обработки
        """
        try:
            meeting_id = f"meeting-{uuid.uuid4()}"
            
            # Шаг 1: Получение транскрипта
            if audio_file:
                logger.info("🎙 Начинаю транскрипцию аудио через Whisper...")
                try:
                    # Сохраняем аудио во временный файл для Whisper
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                        tmp_path = Path(tmp_file.name)
                        tmp_file.write(audio_file)
                        tmp_file.flush()
                    
                    # Транскрибируем через Whisper с retry логикой
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            transcript = await transcription_service.transcribe(tmp_path, language="ru")
                            if transcript and len(transcript.strip()) > 10:
                                logger.info(f"✅ Транскрипция успешна ({len(transcript)} символов)")
                                break
                            else:
                                logger.warning(f"⚠️ Транскрипция вернула пустой или слишком короткий текст (попытка {attempt + 1}/{max_retries})")
                                if attempt < max_retries - 1:
                                    await asyncio.sleep(2)  # Небольшая задержка перед повтором
                        except Exception as transcribe_error:
                            logger.error(f"❌ Ошибка транскрипции (попытка {attempt + 1}/{max_retries}): {transcribe_error}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(2)
                            else:
                                raise
                    
                    # Удаляем временный файл
                    try:
                        os.unlink(tmp_path)
                    except Exception as e:
                        logger.warning(f"Не удалось удалить временный файл {tmp_path}: {e}")
                    
                    if not transcript or len(transcript.strip()) < 10:
                        raise ValueError("Транскрипция не удалась или вернула пустой текст")
                        
                except Exception as e:
                    logger.error(f"❌ Критическая ошибка при транскрипции: {e}")
                    raise ValueError(f"Не удалось транскрибировать аудио: {str(e)}")
            
            if not transcript or len(transcript.strip()) < 10:
                raise ValueError("Необходим transcript (минимум 10 символов) или audio_file")
            
            # Шаг 2-3: Параллельная загрузка RAG и синхронизация контекста из Notion
            logger.info("Параллельная загрузка контекста (RAG + Notion)...")
            
            # Запускаем обе задачи параллельно
            rag_task = self.rag.search_similar_meetings(transcript, limit=3)
            notion_task = self.context_loader.sync_context_from_notion()
            
            similar_meetings, _ = await asyncio.gather(rag_task, notion_task)
            
            context = []
            for meeting in similar_meetings:
                if isinstance(meeting, dict):
                    context.append(meeting.get("content", ""))
                elif isinstance(meeting, str):
                    context.append(meeting)
            
            # Шаг 4: Анализ встречи через Ollama с передачей username
            logger.info("Анализ встречи через Ollama...")
            analysis = await self.ollama.analyze_meeting(
                content=transcript,
                context=context,
                response_schema=MeetingAnalysis,
                sender_username=sender_username
            )
            
            # Шаг 5: Извлечение участников из analysis
            participants = []
            # Используем участников из analysis.participants (основной источник)
            for participant in analysis.participants:
                participants.append({
                    "name": participant.name,
                    "role": participant.role,
                    "matched": False
                })
            
            # Дополнительно извлекаем участников из action_items (если не были найдены в participants)
            existing_names = {p["name"].lower() for p in participants}
            if analysis.action_items:
                for item in analysis.action_items:
                    if item.assignee and item.assignee.lower() not in existing_names:
                        participants.append({
                            "name": item.assignee,
                            "role": None,
                            "matched": False
                        })
                        existing_names.add(item.assignee.lower())
            
            # Шаг 6: Матчинг участников с контактами (с fuzzy matching)
            matched_participants = []
            for participant in participants:
                name = participant["name"]
                # Используем fuzzy matching для более точного поиска
                resolved = self.context_loader.resolve_entity(name, use_fuzzy=True, fuzzy_threshold=0.6)
                if resolved.get("people"):
                    person = resolved["people"][0]
                    match_score = person.get("_match_score", 1.0)
                    matched_name = person.get("_matched_name", name)
                    contact_id = person.get("id")
                    telegram_username = person.get("telegram_username")
                    
                    # Получаем telegram_chat_id из базы данных
                    telegram_chat_id = None
                    if contact_id:
                        try:
                            async with AsyncSessionLocal() as session:
                                # Пробуем найти по notion_page_id (contact_id из Notion)
                                result = await session.execute(
                                    select(Contact).where(Contact.notion_page_id == contact_id)
                                )
                                contact = result.scalar_one_or_none()
                                if contact and contact.telegram_chat_id:
                                    telegram_chat_id = contact.telegram_chat_id
                        except Exception as e:
                            logger.debug(f"Не удалось получить telegram_chat_id для notion_page_id {contact_id}: {e}")
                    
                    # Если не нашли по notion_page_id, пробуем найти по имени или telegram_username
                    if not telegram_chat_id:
                        try:
                            async with AsyncSessionLocal() as session:
                                query = select(Contact)
                                if telegram_username:
                                    query = query.where(Contact.telegram_username == telegram_username)
                                else:
                                    query = query.where(Contact.name.ilike(f"%{person.get('name', name)}%"))
                                
                                result = await session.execute(query)
                                contact = result.scalar_one_or_none()
                                if contact and contact.telegram_chat_id:
                                    telegram_chat_id = contact.telegram_chat_id
                                    logger.info(f"Найден telegram_chat_id для {person.get('name', name)} по имени/username")
                        except Exception as e:
                            logger.debug(f"Не удалось найти telegram_chat_id по имени/username: {e}")
                    
                    matched_participants.append({
                        "name": person.get("name", name),
                        "contact_id": contact_id,
                        "telegram_username": telegram_username,
                        "telegram_chat_id": telegram_chat_id,
                        "matched": True,
                        "match_score": match_score,  # Для отображения в UI
                        "original_name": name,  # Оригинальное имя из транскрипта
                        "matched_name": matched_name  # Имя, по которому был найден матч
                    })
                else:
                    matched_participants.append({
                        "name": name,
                        "matched": False,
                        "original_name": name
                    })
            
            # Шаг 7: Генерация draft follow-up сообщения
            draft_message = analysis.summary_md  # Используем summary как draft
            
            # Примечание: Страница встреч Notion используется только для чтения данных.
            # Запись в неё не выполняется.
            
            # Шаг 8: Инициализация переменных для проектов и предупреждений
            matched_projects = []
            verification_warnings = []
            
            # Шаг 9: Извлечение и присваивание проектов
            try:
                # Получаем проекты из анализа
                extracted_project_keys = analysis.projects if hasattr(analysis, 'projects') else []
                
                # Получаем список проектов из Notion
                projects_from_notion = await self.notion.get_projects_from_db()
                
                if extracted_project_keys and projects_from_notion:
                    # Создаем словарь для быстрого поиска проектов по ключу
                    projects_dict = {p.get("key", "").lower(): p for p in projects_from_notion}
                    
                    # Сопоставляем извлеченные ключи с проектами из Notion
                    for project_key in extracted_project_keys:
                        project_key_lower = project_key.lower()
                        if project_key_lower in projects_dict:
                            project = projects_dict[project_key_lower]
                            matched_projects.append({
                                "key": project.get("key", ""),
                                "name": project.get("name", project.get("key", "")),
                                "id": project.get("id"),
                                "matched": True
                            })
                            logger.info(f"Проект '{project_key}' найден и присвоен встрече")
                        else:
                            matched_projects.append({
                                "key": project_key,
                                "name": project_key,
                                "matched": False
                            })
                            verification_warnings.append(f"⚠️ Проект '{project_key}' не найден в базе 'Проекты'")
                
                # Сверяем участников
                for participant in matched_participants:
                    if not participant.get("matched"):
                        verification_warnings.append(f"⚠️ Участник '{participant['name']}' не найден в базе 'Люди'")
            except Exception as e:
                logger.warning(f"Ошибка при извлечении и присваивании проектов: {e}")
            
            # Шаг 9.5: Проверка терминов глоссария
            try:
                # Ищем термины глоссария в транскрипте и саммари
                combined_text = f"{transcript}\n{analysis.summary_md if hasattr(analysis, 'summary_md') else ''}"
                found_glossary_terms = self.context_loader.find_glossary_terms(combined_text)
                
                if found_glossary_terms:
                    logger.info(f"Найдено {len(found_glossary_terms)} терминов из глоссария: {', '.join(found_glossary_terms.keys())}")
                else:
                    logger.debug("Термины глоссария не найдены в тексте встречи")
                
                # Если глоссарий не пустой, но термины не найдены - это не ошибка, просто информация
                # Можно добавить предупреждение, если нужно проверять использование правильных терминов
            except Exception as e:
                logger.warning(f"Ошибка при проверке терминов глоссария: {e}")
            
            # Шаг 10: Сохранение в SQLite
            action_items_data = [
                {
                    "text": item.text,
                    "assignee": item.assignee,
                    "priority": item.priority
                }
                for item in analysis.action_items
            ]
            
            # Извлекаем расширенные данные из анализа
            key_decisions_data = [
                {
                    "title": decision.title,
                    "description": decision.description,
                    "impact": decision.impact
                }
                for decision in (analysis.key_decisions if hasattr(analysis, 'key_decisions') else [])
            ]
            
            insights_data = analysis.insights if hasattr(analysis, 'insights') else []
            next_steps_data = analysis.next_steps if hasattr(analysis, 'next_steps') else []
            
            async with AsyncSessionLocal() as session:
                meeting = Meeting(
                    id=meeting_id,
                    transcript=transcript,
                    summary=analysis.summary_md,
                    participants=matched_participants,
                    projects=matched_projects,
                    action_items=action_items_data,
                    key_decisions=key_decisions_data,
                    insights=insights_data,
                    next_steps=next_steps_data,
                    draft_message=draft_message,
                    status="pending_approval",  # Требует согласования перед отправкой
                    notion_page_id=notion_page_id  # Сохраняем только переданный ID для связи, не создаем/не пишем в страницу
                )
                session.add(meeting)
                await session.commit()
                await session.refresh(meeting)
            
            logger.info(f"Встреча сохранена со статусом pending_approval: {meeting_id}")
            
            # Шаг 11: Сохранение в RAG для будущих поисков
            try:
                # Сериализуем списки в строки для ChromaDB (metadata должен содержать только скалярные значения)
                participants_str = ", ".join([p["name"] for p in matched_participants]) if matched_participants else ""
                
                await self.rag.add_meeting(
                    meeting_id=meeting_id,
                    content=transcript,
                    metadata={
                        "summary": analysis.summary_md[:500] if analysis.summary_md else "",  # Ограничиваем длину
                        "participants": participants_str
                    }
                )
            except Exception as e:
                logger.error(f"Ошибка при добавлении встречи в RAG: {e}")
            
            # Шаг 12: НЕ отправляем автоматически - требуется согласование
            # Отправка будет выполнена через отдельный endpoint после согласования
            
            return {
                "meeting_id": meeting_id,
                "transcript": transcript,
                "summary": analysis.summary_md,
                "participants": matched_participants,
                "projects": matched_projects,
                "draft_message": draft_message,
                "action_items": [
                    {
                        "text": item.text,
                        "assignee": item.assignee,
                        "priority": item.priority
                    }
                    for item in analysis.action_items
                ],
                "key_decisions": key_decisions_data,
                "insights": insights_data,
                "next_steps": next_steps_data,
                "verification_warnings": verification_warnings,
                "requires_approval": True,
                "status": "pending_approval",
                "message": "Встреча обработана и ожидает согласования перед отправкой"
            }
            
        except Exception as e:
            logger.error(f"Ошибка при обработке встречи: {e}")
            raise
    
    def extract_tags(
        self,
        transcript: str,
        projects: List[Dict[str, Any]],
        action_items: List[Dict[str, Any]],
        participants: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        """
        Извлекает теги из встречи для организации.
        
        Args:
            transcript: Транскрипт встречи
            projects: Список проектов из встречи
            action_items: Список задач
            participants: Список участников (опционально)
            
        Returns:
            Список тегов (например: ['crm', 'ai-integration', 'design'])
        """
        tags = []
        
        # Теги из проектов
        for project in projects:
            if isinstance(project, dict):
                project_key = project.get('key', '')
                project_name = project.get('name', '')
                if project_key:
                    # Используем ключ проекта как тег (например, "CRM" -> "crm")
                    tag = project_key.lower().replace(' ', '-').replace('_', '-')
                    if tag and tag not in tags:
                        tags.append(tag)
                elif project_name:
                    # Если нет ключа, используем имя проекта
                    tag = project_name.lower().replace(' ', '-').replace('_', '-')
                    if tag and tag not in tags:
                        tags.append(tag)
        
        # Теги из action_items (извлекаем ключевые слова)
        common_tech_keywords = [
            'ai', 'ml', 'crm', 'api', 'ui', 'ux', 'design', 'frontend', 'backend',
            'database', 'integration', 'automation', 'workflow', 'notion',
            'telegram', 'openai', 'ollama', 'whisper', 'transcription'
        ]
        
        # Объединяем текст из action_items для анализа
        action_text = ' '.join([
            item.get('text', '') or item.get('title', '') or str(item)
            for item in action_items
        ]).lower()
        
        # Ищем ключевые слова в задачах
        for keyword in common_tech_keywords:
            if keyword in action_text and keyword not in tags:
                tags.append(keyword)
        
        # Теги из транскрипта (ищем упоминания технологий и проектов)
        transcript_lower = transcript.lower()
        for keyword in common_tech_keywords:
            if keyword in transcript_lower and keyword not in tags:
                tags.append(keyword)
        
        # Извлекаем теги из упоминаний проектов в транскрипте
        # Ищем паттерны типа "проект X", "в проекте Y"
        import re
        project_patterns = [
            r'проект[ае]?\s+([a-zа-яё]+)',
            r'в\s+проекте\s+([a-zа-яё]+)',
            r'проект\s+"([^"]+)"',
        ]
        
        for pattern in project_patterns:
            matches = re.findall(pattern, transcript_lower)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                tag = match.strip().lower().replace(' ', '-')
                if tag and len(tag) > 2 and tag not in tags:
                    tags.append(tag)
        
        # Ограничиваем количество тегов (максимум 10)
        tags = tags[:10]
        
        logger.info(f"Извлечено тегов: {tags}")
        return tags
