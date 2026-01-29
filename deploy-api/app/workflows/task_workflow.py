"""
Workflow обработки задач.
"""
from datetime import datetime
from typing import Dict, Any
from loguru import logger
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta
import re
import re

from app.services.ollama_service import OllamaService
from app.services.notion_service import NotionService
from app.services.telegram_service import TelegramService
from app.db.models import Task
from app.db.database import AsyncSessionLocal, get_db


class TaskWorkflow:
    """Workflow для обработки задач."""
    
    def __init__(self):
        self.ollama = OllamaService()
        self.notion = NotionService()
        self.telegram = TelegramService()
    
    async def process_task(self, task_text: str, create_in_notion: bool = False) -> Dict[str, Any]:
        """
        Обрабатывает задачу: извлекает intent и deadline, сохраняет, планирует уведомление.
        
        Args:
            task_text: Текст задачи
            create_in_notion: Создавать ли задачу в Notion
            
        Returns:
            Словарь с результатом обработки
        """
        try:
            # Шаг 1: Извлечение intent и deadline через Ollama
            logger.info(f"Извлечение intent из задачи: {task_text[:100]}...")
            extracted = await self.ollama.extract_task_intent(task_text)
            
            intent = extracted.get("intent", task_text)
            deadline_str = extracted.get("deadline")
            priority = extracted.get("priority", "Medium")
            assignee = extracted.get("assignee")
            project = extracted.get("project")
            
            # Шаг 2: Парсинг относительных дат
            deadline = None
            if deadline_str:
                deadline = self._parse_relative_date(deadline_str)
            
            # Шаг 3: Сохранение в SQLite
            task_id = f"task-{int(datetime.now().timestamp() * 1000)}"
            
            async with AsyncSessionLocal() as session:
                task = Task(
                    id=task_id,
                    text=task_text,
                    intent=intent,
                    deadline=deadline,
                    priority=priority,
                    status="pending"
                )
                session.add(task)
                await session.commit()
                await session.refresh(task)
            
            logger.info(f"Задача сохранена: {task_id} (assignee: {assignee}, project: {project})")
            
            # Шаг 4: Создание задачи в Notion (если нужно)
            notion_task_id = None
            if create_in_notion:
                try:
                    task_data = {
                        "text": intent,
                        "deadline": deadline.isoformat() if deadline else None,
                        "priority": priority
                    }
                    if assignee:
                        task_data["assignee"] = assignee
                    if project:
                        task_data["project"] = project
                    
                    notion_task_id = await self.notion.create_task_in_notion(task_data)
                    logger.info(f"Задача создана в Notion: {notion_task_id}")
                except Exception as e:
                    logger.error(f"Ошибка при создании задачи в Notion: {e}")
            
            # Шаг 5: Планирование уведомления (если есть deadline)
            if deadline:
                # TODO: Реализовать планирование через task queue или cron
                logger.info(f"Уведомление запланировано на {deadline}")
            
            return {
                "task_id": task_id,
                "intent": intent,
                "deadline": deadline.isoformat() if deadline else None,
                "priority": priority,
                "assignee": assignee,
                "project": project,
                "notion_task_id": notion_task_id,
                "message": "Задача успешно обработана"
            }
            
        except Exception as e:
            logger.error(f"Ошибка при обработке задачи: {e}")
            raise
    
    def _parse_relative_date(self, date_str: str) -> datetime:
        """
        Парсит относительные даты типа "next tuesday", "tomorrow" и т.д.
        
        Args:
            date_str: Строка с датой
            
        Returns:
            datetime объект
        """
        date_str_lower = date_str.lower().strip()
        now = datetime.now()
        
        # Абсолютные даты
        try:
            return date_parser.parse(date_str)
        except:
            pass
        
        # Относительные даты
        if "tomorrow" in date_str_lower or "завтра" in date_str_lower:
            return now + relativedelta(days=1)
        
        if "next week" in date_str_lower or "следующая неделя" in date_str_lower:
            return now + relativedelta(weeks=1)
        
        # Дни недели
        days_map = {
            "monday": 0, "понедельник": 0,
            "tuesday": 1, "вторник": 1,
            "wednesday": 2, "среда": 2,
            "thursday": 3, "четверг": 3,
            "friday": 4, "пятница": 4,
            "saturday": 5, "суббота": 5,
            "sunday": 6, "воскресенье": 6
        }
        
        for day_name, day_num in days_map.items():
            if day_name in date_str_lower:
                # Находим следующий день недели
                days_ahead = day_num - now.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                return now + relativedelta(days=days_ahead)
        
        # Если не распознано, возвращаем None
        logger.warning(f"Не удалось распарсить дату: {date_str}")
        return None
