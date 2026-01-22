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
from app.models.schemas import MeetingAnalysis
from app.db.models import Meeting, Contact
from app.db.database import AsyncSessionLocal
from app.config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


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
        notion_page_id: Optional[str] = None
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
                # TODO: Реализовать транскрипцию через Ollama Whisper или другой сервис
                logger.warning("Транскрипция аудио пока не реализована, используем переданный transcript")
                transcript = transcript or ""
            
            if not transcript:
                raise ValueError("Необходим transcript или audio_file")
            
            # Шаг 2-3: Параллельная загрузка RAG и синхронизация контекста из Notion
            import asyncio
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
            
            # Шаг 4: Анализ встречи через Ollama
            logger.info("Анализ встречи через Ollama...")
            analysis = await self.ollama.analyze_meeting(
                content=transcript,
                context=context,
                response_schema=MeetingAnalysis
            )
            
            # Шаг 5: Извлечение участников (из analysis или через NER)
            participants = []
            if analysis.action_items:
                # Извлекаем участников из action_items
                for item in analysis.action_items:
                    if item.assignee:
                        participants.append({
                            "name": item.assignee,
                            "matched": False
                        })
            
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
            
            async with AsyncSessionLocal() as session:
                meeting = Meeting(
                    id=meeting_id,
                    transcript=transcript,
                    summary=analysis.summary_md,
                    participants=matched_participants,
                    projects=matched_projects,
                    action_items=action_items_data,
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
                "verification_warnings": verification_warnings,
                "requires_approval": True,
                "status": "pending_approval",
                "message": "Встреча обработана и ожидает согласования перед отправкой"
            }
            
        except Exception as e:
            logger.error(f"Ошибка при обработке встречи: {e}")
            raise
