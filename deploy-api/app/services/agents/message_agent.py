"""
Агент для отложенных сообщений.
"""
from typing import Dict, Any, List, Optional
from loguru import logger
from datetime import datetime

from app.services.agents.base_agent import BaseAgent
from app.models.schemas import IntentClassification


def _looks_like_chat_id(s: str) -> bool:
    """Проверяет, похожа ли строка на telegram chat_id (число или число с минусом)."""
    if not s or not isinstance(s, str):
        return False
    s = s.strip()
    return s.lstrip("-").isdigit()


class MessageAgent(BaseAgent):
    """Агент для обработки отложенных сообщений."""
    
    def __init__(self):
        super().__init__()
    
    def get_agent_type(self) -> str:
        return "message"
    
    async def _resolve_recipient_to_chat_id(self, recipient: str, sender_chat_id: Optional[str]) -> Optional[str]:
        """
        Резолвит получателя в telegram chat_id.
        — Если recipient уже похож на chat_id — возвращает его.
        — «Мне»/«себе»/«не указан» → sender_chat_id.
        — Иначе ищет контакт по имени/username/aliases в БД и возвращает telegram_chat_id.
        """
        if not recipient or str(recipient).strip() in ("не указан", "мне", "себе", "мне же", "сюда"):
            return sender_chat_id
        r = str(recipient).strip().lower()
        if _looks_like_chat_id(r):
            return r
        try:
            from app.db.database import AsyncSessionLocal
            from app.db.models import Contact
            from sqlalchemy import select, or_
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Contact).where(
                        Contact.telegram_chat_id.isnot(None),
                        or_(
                            Contact.name.ilike(f"%{r}%"),
                            Contact.telegram_username.ilike(f"%{r}%"),
                            Contact.telegram_username.ilike(f"%@{r}%")
                        )
                    ).limit(1)
                )
                contact = result.scalar_one_or_none()
                if contact and contact.telegram_chat_id:
                    return str(contact.telegram_chat_id)
                # по aliases (JSON массив)
                result = await db.execute(select(Contact).where(Contact.telegram_chat_id.isnot(None)))
                for c in result.scalars().all():
                    aliases = c.aliases or []
                    if any(r in str(a).lower() for a in aliases):
                        return str(c.telegram_chat_id)
        except Exception as e:
            logger.debug(f"Резолв recipient→chat_id: {e}")
        return sender_chat_id
    
    async def _process_with_context(
        self,
        user_input: str,
        classification: IntentClassification,
        context: List[str],
        sender_username: str = None,
        sender_chat_id: str = None
    ) -> Dict[str, Any]:
        """
        Обрабатывает отложенное сообщение.
        Целевой chat_id: резолв recipient по контактам или sender_chat_id (напомни мне / в этот чат).
        """
        try:
            extracted_data = classification.extracted_data
            
            # Извлекаем получателя и время отправки
            recipient = extracted_data.get("recipient", "не указан")
            send_time = extracted_data.get("send_time", "не указано")
            message_text = extracted_data.get("message", user_input)
            
            # Куда слать: резолвим recipient → telegram_chat_id по контактам, иначе — чат отправителя
            target_chat_id = await self._resolve_recipient_to_chat_id(recipient, sender_chat_id)
            if not target_chat_id:
                target_chat_id = sender_chat_id
            if not target_chat_id:
                logger.warning("Отложенное сообщение: не задан target_chat_id (ни recipient, ни sender_chat_id). Планирование пропущено.")
            
            # Сохраняем отложенное сообщение через SchedulerService
            try:
                if not target_chat_id:
                    raise ValueError("Неизвестно, куда отправить отложенное сообщение")
                from app.services.scheduler_service import get_scheduler_service
                from app.services.date_parser_service import get_date_parser_service
                from datetime import datetime, timedelta
                
                scheduler = get_scheduler_service()
                date_parser = get_date_parser_service()
                
                # Парсим время отправки с помощью улучшенного парсера
                send_datetime = None
                if send_time and send_time != "не указано":
                    send_datetime = date_parser.parse_datetime(send_time)
                
                if not send_datetime:
                    send_datetime = datetime.now() + timedelta(hours=1)  # По умолчанию через час
                
                # Планируем отправку сообщения — в замыкании передаём конкретный chat_id и текст
                task_id = f"message-{target_chat_id}-{send_datetime.isoformat()}"
                _chat_id = str(target_chat_id)
                _text = str(message_text)
                
                async def send_scheduled_message():
                    from app.services.telegram_service import TelegramService
                    telegram = TelegramService()
                    await telegram.send_message_to_user(chat_id=_chat_id, message=_text, parse_mode="HTML")
                
                scheduler.schedule_task(
                    task_id=task_id,
                    execute_at=send_datetime,
                    action=send_scheduled_message,
                    action_args={}
                )
                
                logger.info(f"Сообщение запланировано на {send_datetime}")
                
            except Exception as e:
                logger.warning(f"Не удалось запланировать сообщение через SchedulerService: {e}")
                # Продолжаем выполнение даже при ошибке планирования
            
            # Формируем ответ через персону
            context_info = f"""
            Отложенное сообщение запланировано.
            Получатель: {recipient}
            Время: {send_time}
            Текст: {message_text[:100]}...
            """
            
            # Используем уже инициализированный OllamaService из BaseAgent
            response_text = await self.ollama.generate_persona_response(
                user_input=f"Запланируй сообщение: {user_input}",
                context=context_info
            )
            
            # Добавляем эмодзи если их нет, для соответствия стилю
            if "🤖" not in response_text and "✅" not in response_text:
                response_text = f"✅ {response_text}"
            
            return {
                "response": response_text,
                "actions": [
                    {
                        "type": "message_scheduled",
                        "recipient": recipient,
                        "send_time": send_time
                    }
                ],
                "metadata": {
                    "recipient": recipient,
                    "send_time": send_time,
                    "message": message_text
                },
                "should_save_to_rag": True
            }
            
        except Exception as e:
            logger.error(f"Ошибка в MessageAgent: {e}")
            return {
                "response": f"❌ Ошибка при планировании сообщения: {str(e)}",
                "actions": [],
                "metadata": {"error": str(e)},
                "should_save_to_rag": False
            }
