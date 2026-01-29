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


class DailyCheckinService:
    """Сервис для ежедневных опросов."""
    
    def __init__(self):
        self.telegram = TelegramService()
        self.ollama = OllamaService()
        from app.services.notion_service import NotionService
        self.notion = NotionService()
    
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
    
    async def _generate_daily_question(self, name: str, tov_style: str) -> str:
        """
        Генерирует вопрос для daily check-in с учетом Tone of Voice.
        
        Args:
            name: Имя контакта
            tov_style: Стиль общения ("formal", "friendly", "brief", "default")
            
        Returns:
            Сгенерированный вопрос
        """
        tov_prompts = {
            "formal": "Официальный, деловой стиль. Вежливо, но без лишних слов.",
            "friendly": "Дружелюбный, неформальный стиль. Можно использовать 'ты', эмодзи, но не перебарщивай.",
            "brief": "Максимально краткий. Без приветствий, сразу к делу. 1-2 предложения.",
            "default": "Нейтральный стиль. Кратко, по делу, без лишних формальностей."
        }
        
        tov_description = tov_prompts.get(tov_style.lower(), tov_prompts["default"])
        
        prompt = f"""Сгенерируй вопрос для ежедневного опроса сотрудника {name}.

Стиль общения: {tov_description}

Вопрос должен быть про "что сделано за день?" в разных формулировках в зависимости от стиля.

ВАЖНО:
- Вопрос должен быть на русском языке
- Используй имя {name} в обращении
- Вопрос должен мотивировать ответить конкретно о выполненной работе
- Не используй нумерованные списки (1, 2, 3)
- Один вопрос, максимум 2-3 предложения

Примеры для разных стилей:
- formal: "Добрый день, {name}. Пожалуйста, поделитесь, какие задачи были выполнены сегодня?"
- friendly: "Привет, {name}! Что успел сделать за день?"
- brief: "{name}, что сделано?"
- default: "{name}, что сделал за день?"

Сгенерируй вопрос в стиле {tov_style}:"""
        
        try:
            # Используем асинхронный клиент Ollama
            response = await self.ollama.client.chat(
                model=self.ollama.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "Ты помощник, который генерирует вопросы для ежедневных отчетов. Отвечай только текстом вопроса, без дополнительных комментариев."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                options={
                    "temperature": 0.7,
                    "num_predict": 150
                }
            )
            
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                question = response.message.content.strip()
            elif isinstance(response, dict):
                question = response.get('message', {}).get('content', '').strip()
            else:
                question = str(response).strip()
            
            # Если ответ пустой или слишком короткий, используем дефолтный
            if not question or len(question) < 10:
                question = f"{name}, что сделано за день?"
            
            logger.info(f"Сгенерирован вопрос для {name} в стиле {tov_style}: {question[:50]}...")
            return question
            
        except Exception as e:
            logger.error(f"Ошибка при генерации вопроса для {name}: {e}")
            # Fallback на простой вопрос
            return f"{name}, что сделано за день?"
    
    async def get_team_contacts(self, db: AsyncSession) -> List[Contact]:
        """
        Получить контакты команды из Notion People DB с фильтрацией по is_active.
        Синхронизирует данные из Notion в локальную БД перед возвратом.
        """
        try:
            # Получаем список активных контактов из Notion
            notion_contacts = await self.notion.get_contacts_from_db()
            
            # Фильтруем только активных для daily check-in
            active_notion_contacts = [
                c for c in notion_contacts 
                if c.get("is_active", "true").lower() == "true" and c.get("telegram_username") or c.get("name")
            ]
            
            logger.info(f"Найдено {len(active_notion_contacts)} активных контактов в Notion для daily check-in")
            
            # Синхронизируем с локальной БД и получаем Contact объекты
            contacts = []
            for notion_contact in active_notion_contacts:
                notion_page_id = notion_contact.get("id")
                name = notion_contact.get("name", "")
                
                if not name:
                    continue
                
                # Ищем контакт в локальной БД по notion_page_id
                result = await db.execute(
                    select(Contact).where(Contact.notion_page_id == notion_page_id)
                )
                contact = result.scalar_one_or_none()
                
                # Если не найден, создаем новый
                if not contact:
                    # Пробуем найти по имени или telegram_username
                    telegram_username = notion_contact.get("telegram_username", "")
                    if telegram_username:
                        result = await db.execute(
                            select(Contact).where(Contact.telegram_username == telegram_username)
                        )
                        contact = result.scalar_one_or_none()
                    
                    if not contact:
                        result = await db.execute(
                            select(Contact).where(Contact.name.ilike(f"%{name}%"))
                        )
                        contact = result.scalar_one_or_none()
                
                # Обновляем или создаем контакт
                if contact:
                    # Обновляем данные из Notion
                    contact.name = name
                    contact.telegram_username = notion_contact.get("telegram_username", "")
                    contact.aliases = notion_contact.get("aliases", [])
                    contact.tov_style = notion_contact.get("tov_style", "default")
                    contact.is_active = notion_contact.get("is_active", "true")
                    contact.notion_page_id = notion_page_id
                    contact.last_synced = datetime.now()
                else:
                    # Создаем новый контакт
                    from uuid import uuid4
                    contact = Contact(
                        id=str(uuid4()),
                        name=name,
                        telegram_username=notion_contact.get("telegram_username", ""),
                        aliases=notion_contact.get("aliases", []),
                        tov_style=notion_contact.get("tov_style", "default"),
                        is_active=notion_contact.get("is_active", "true"),
                        notion_page_id=notion_page_id
                    )
                    db.add(contact)
                
                await db.commit()
                
                # Добавляем только если есть telegram_chat_id (иначе не сможем отправить сообщение)
                if contact.telegram_chat_id:
                    contacts.append(contact)
                else:
                    logger.warning(f"У контакта {name} нет telegram_chat_id, пропускаем для daily check-in")
            
            logger.info(f"Подготовлено {len(contacts)} контактов для отправки daily check-in")
            return contacts
            
        except Exception as e:
            logger.error(f"Ошибка при получении контактов из Notion: {e}")
            # Fallback: возвращаем контакты из локальной БД
            result = await db.execute(
                select(Contact).where(
                    Contact.is_active == "true",
                    Contact.telegram_chat_id.isnot(None)
                )
            )
            return result.scalars().all()
    
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
                
                # Генерируем вопрос с учетом Tone of Voice
                tov_style = contact.tov_style or "default"
                question = await self._generate_daily_question(contact.name, tov_style)
                
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
        
        # Категоризируем ответ через LLM для определения статуса
        try:
            status_category = await self._categorize_response(response_text)
        except Exception as e:
            logger.warning(f"Ошибка при категоризации ответа: {e}")
            status_category = "Выполнено"  # Дефолтный статус
        
        # Сохраняем в Notion Daily Reports
        try:
            # Извлекаем упомянутые задачи из ответа
            tasks_mentioned = await self._extract_tasks_from_response(response_text)
            
            await self.notion.save_daily_report(
                contact_name=contact.name,
                response_text=response_text,
                checkin_date=checkin.checkin_date,
                status=status_category,
                tasks_mentioned=tasks_mentioned
            )
            logger.info(f"✅ Daily report сохранен в Notion для {contact.name}")
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении daily report в Notion: {e}")
            # Не прерываем выполнение, если сохранение в Notion не удалось
        
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
    
    async def _categorize_response(self, response_text: str) -> str:
        """
        Категоризирует ответ daily check-in через LLM.
        
        Returns:
            Статус: "Выполнено", "В процессе", "Проблема"
        """
        prompt = f"""Проанализируй следующий ответ на ежедневный опрос и определи статус:

Ответ: {response_text[:500]}

Определи статус:
- "Выполнено" - если упоминаются завершенные задачи, достижения, успехи
- "В процессе" - если упоминаются задачи в работе, планы, текущая активность
- "Проблема" - если упоминаются блокеры, проблемы, задержки, трудности

Ответь только одним словом: Выполнено, В процессе, или Проблема."""
        
        try:
            response = await self.ollama.client.chat(
                model=self.ollama.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "Ты классификатор ответов. Отвечай только одним словом: Выполнено, В процессе, или Проблема."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                options={
                    "temperature": 0.3,
                    "num_predict": 20
                }
            )
            
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                category = response.message.content.strip()
            elif isinstance(response, dict):
                category = response.get('message', {}).get('content', '').strip()
            else:
                category = str(response).strip()
            
            # Нормализуем ответ
            category_lower = category.lower()
            if "проблем" in category_lower or "блок" in category_lower or "задерж" in category_lower:
                return "Проблема"
            elif "процесс" in category_lower or "работа" in category_lower or "план" in category_lower:
                return "В процессе"
            else:
                return "Выполнено"
                
        except Exception as e:
            logger.error(f"Ошибка при категоризации ответа: {e}")
            return "Выполнено"
    
    async def _extract_tasks_from_response(self, response_text: str) -> List[str]:
        """
        Извлекает упомянутые задачи из ответа через LLM.
        
        Returns:
            Список задач
        """
        prompt = f"""Извлеки все упомянутые задачи из следующего ответа:

Ответ: {response_text[:500]}

Верни список задач, по одной на строку. Если задач нет, верни пустую строку."""
        
        try:
            response = await self.ollama.client.chat(
                model=self.ollama.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "Ты извлекаешь задачи из текста. Верни список задач, по одной на строку."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                options={
                    "temperature": 0.3,
                    "num_predict": 200
                }
            )
            
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                tasks_text = response.message.content.strip()
            elif isinstance(response, dict):
                tasks_text = response.get('message', {}).get('content', '').strip()
            else:
                tasks_text = str(response).strip()
            
            # Парсим список задач
            tasks = [t.strip() for t in tasks_text.split('\n') if t.strip() and len(t.strip()) > 5]
            return tasks[:10]  # Максимум 10 задач
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении задач из ответа: {e}")
            return []
    
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
