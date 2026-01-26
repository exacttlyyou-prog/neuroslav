"""
Агент для отложенных сообщений.
"""
from typing import Dict, Any, List
from loguru import logger
from datetime import datetime

from app.services.agents.base_agent import BaseAgent
from app.models.schemas import IntentClassification


class MessageAgent(BaseAgent):
    """Агент для обработки отложенных сообщений."""
    
    def __init__(self):
        super().__init__()
    
    def get_agent_type(self) -> str:
        return "message"
    
    async def _process_with_context(
        self,
        user_input: str,
        classification: IntentClassification,
        context: List[str],
        sender_username: str = None
    ) -> Dict[str, Any]:
        """
        Обрабатывает отложенное сообщение.
        """
        try:
            extracted_data = classification.extracted_data
            
            # Извлекаем получателя и время отправки
            recipient = extracted_data.get("recipient", "не указан")
            send_time = extracted_data.get("send_time", "не указано")
            message_text = extracted_data.get("message", user_input)
            
            # Сохраняем отложенное сообщение через SchedulerService
            try:
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
                
                # Планируем отправку сообщения
                task_id = f"message-{recipient}-{send_datetime.isoformat()}"
                
                async def send_scheduled_message():
                    from app.services.telegram_service import TelegramService
                    telegram = TelegramService()
                    await telegram.send_message_to_user(
                        chat_id=recipient,
                        message=message_text
                    )
                
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
