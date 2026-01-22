"""
Сервис для ежедневных опросов команды.
"""
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from uuid import uuid4
from loguru import logger

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.services.telegram_service import TelegramService
from app.services.ollama_service import OllamaService
from app.db.models import Contact, DailyCheckin


# Список людей из ИИ в контенте
TEAM_MEMBERS = [
    "Иван",
    "Михаил",
    "Вячеслав",
    "Кристина",
    "Алексей",
    "Сергей",
    "Максим",
    "Гриша",
    "Полина Молчанова",
    "Полина Кухтенкова",
    "Данил"
]


class DailyCheckinService:
    """Сервис для ежедневных опросов."""
    
    def __init__(self):
        self.telegram = TelegramService()
        self.ollama = OllamaService()
    
    async def _generate_text(self, prompt: str) -> str:
        """Генерирует текст через Ollama."""
        import asyncio
        # ollama.client.chat синхронный, поэтому используем executor
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.ollama.client.chat(
                model=self.ollama.model_name,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.7, "num_predict": 200}
            )
        )
        
        if isinstance(response, dict):
            return response.get('message', {}).get('content', '')
        return str(response)
    
    async def get_team_contacts(self, db: AsyncSession) -> List[Contact]:
        """Получить контакты команды из ИИ в контенте."""
        contacts = []
        for name in TEAM_MEMBERS:
            # Ищем по имени или алиасам
            result = await db.execute(
                select(Contact).where(
                    Contact.name.ilike(f"%{name}%")
                )
            )
            contact = result.scalar_one_or_none()
            if not contact:
                # Пробуем найти по алиасам
                result = await db.execute(select(Contact))
                all_contacts = result.scalars().all()
                for c in all_contacts:
                    aliases = c.aliases or []
                    if any(name.lower() in str(alias).lower() for alias in aliases):
                        contact = c
                        break
            
            if contact and contact.telegram_chat_id:
                contacts.append(contact)
            else:
                logger.warning(f"Не найден контакт или chat_id для {name}")
        
        return contacts
    
    async def send_daily_questions(self, db: AsyncSession) -> Dict[str, int]:
        """
        Отправить ежедневные вопросы всем членам команды.
        
        Returns:
            Словарь с результатами: {"sent": количество, "failed": количество}
        """
        contacts = await self.get_team_contacts(db)
        
        # Определяем текущий день (начало дня)
        today = datetime.now()
        checkin_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
        
        results = {"sent": 0, "failed": 0}
        
        for contact in contacts:
            try:
                # Проверяем, не отправляли ли уже вопрос на сегодня
                result = await db.execute(
                    select(DailyCheckin).where(
                        and_(
                            DailyCheckin.contact_id == contact.id,
                            DailyCheckin.checkin_date == checkin_date
                        )
                    )
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    logger.info(f"Вопрос для {contact.name} уже отправлен сегодня")
                    continue
                
                # Создаем запись опроса
                checkin = DailyCheckin(
                    id=str(uuid4()),
                    contact_id=contact.id,
                    checkin_date=checkin_date,
                    status="pending"
                )
                db.add(checkin)
                
                # Формируем вопрос
                question = (
                    f"Привет, {contact.name}! 👋\n\n"
                    f"Ежедневный опрос:\n\n"
                    f"1. Что сделали за день?\n"
                    f"2. Какие были проблемы?\n"
                    f"3. Какой планируется следующий шаг?\n\n"
                    f"Ответь, пожалуйста, на эти вопросы."
                )
                
                # Отправляем сообщение
                await self.telegram.send_message_to_user(
                    chat_id=contact.telegram_chat_id,
                    message=question
                )
                
                checkin.question_sent_at = datetime.now()
                checkin.status = "sent"
                await db.commit()
                
                results["sent"] += 1
                logger.info(f"Вопрос отправлен {contact.name}")
                
            except Exception as e:
                logger.error(f"Ошибка при отправке вопроса {contact.name}: {e}")
                results["failed"] += 1
                await db.rollback()
        
        return results
    
    async def process_response(
        self,
        chat_id: str,
        response_text: str,
        db: AsyncSession
    ) -> Optional[str]:
        """
        Обработать ответ на еженедельный опрос.
        
        Args:
            chat_id: Chat ID пользователя
            response_text: Текст ответа
            db: Сессия БД
            
        Returns:
            Текст уточняющего вопроса или None, если уточнение не нужно
        """
        # Находим контакт по chat_id
        result = await db.execute(
            select(Contact).where(Contact.telegram_chat_id == chat_id)
        )
        contact = result.scalar_one_or_none()
        
        if not contact:
            logger.warning(f"Контакт не найден для chat_id: {chat_id}")
            return None
        
        # Находим активный опрос
        today = datetime.now()
        checkin_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
        
        result = await db.execute(
            select(DailyCheckin).where(
                and_(
                    DailyCheckin.contact_id == contact.id,
                    DailyCheckin.checkin_date == checkin_date,
                    DailyCheckin.status.in_(["sent", "responded"])
                )
            )
        )
        checkin = result.scalar_one_or_none()
        
        if not checkin:
            logger.warning(f"Активный опрос не найден для {contact.name}")
            return None
        
        # Сохраняем ответ
        checkin.response_text = response_text
        checkin.response_received_at = datetime.now()
        checkin.status = "responded"
        await db.commit()
        
        # Проверяем, нужно ли уточнение через AI
        clarification = await self._check_if_clarification_needed(response_text)
        
        if clarification:
            checkin.clarification_asked += 1
            await db.commit()
            return clarification
        
        # Если уточнение не нужно, помечаем как завершенный
        checkin.status = "completed"
        await db.commit()
        
        return None
    
    async def _check_if_clarification_needed(self, response_text: str) -> Optional[str]:
        """
        Проверить через AI, нужно ли уточнение задачи.
        
        Args:
            response_text: Текст ответа
            
        Returns:
            Текст уточняющего вопроса или None
        """
        prompt = (
            f"Проанализируй следующий ответ на ежедневный опрос:\n\n"
            f"{response_text}\n\n"
            f"Определи, есть ли в ответе упоминания задач или планов, которые:\n"
            f"1. Недостаточно понятны (нет контекста, деталей, сроков)\n"
            f"2. Требуют уточнения для понимания\n\n"
            f"Если такие задачи есть, сформулируй краткий уточняющий вопрос на русском языке.\n"
            f"Если все понятно, ответь только 'OK'."
        )
        
        try:
            # Используем простой вызов chat для генерации текста
            response_text = await self._generate_text(prompt)
            response_text = response_text.strip()
            
            if response_text.upper() == "OK" or len(response_text) < 10:
                return None
            
            return response_text
        except Exception as e:
            logger.error(f"Ошибка при проверке уточнения: {e}")
            return None
