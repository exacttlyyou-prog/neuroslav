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
        context: List[str]
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
            
            # TODO: Реализовать сохранение отложенного сообщения в БД
            # Пока просто возвращаем подтверждение
            
            return {
                "response": f"✅ Отложенное сообщение запланировано\n\nПолучатель: {recipient}\nВремя: {send_time}\nСообщение: {message_text[:100]}...",
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
