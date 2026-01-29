"""
Агент по умолчанию для общих ответов.
"""
from typing import Dict, Any, List
from loguru import logger

from app.services.agents.base_agent import BaseAgent
from app.services.ollama_service import OllamaService
from app.models.schemas import IntentClassification


class DefaultAgent(BaseAgent):
    """Агент по умолчанию для общих ответов и помощи."""
    
    def __init__(self):
        super().__init__()
        # self.ollama уже инициализирован в BaseAgent, не нужно дублировать
    
    def get_agent_type(self) -> str:
        return "default"
    
    async def _process_with_context(
        self,
        user_input: str,
        classification: IntentClassification,
        context: List[str],
        sender_username: str = None,
        sender_chat_id: str = None
    ) -> Dict[str, Any]:
        """
        Обрабатывает общий запрос или вопрос.
        """
        try:
            # Используем LLM для генерации ответа в стиле персоны
            response_text = await self.ollama.generate_persona_response(
                user_input=user_input,
                context=""
            )
            
            return {
                "response": response_text,
                "actions": [],
                "metadata": {
                    "type": "general_response"
                },
                "should_save_to_rag": False
            }
            
        except Exception as e:
            logger.error(f"Ошибка в DefaultAgent: {e}")
            return {
                "response": "Извините, не могу обработать этот запрос. Попробуйте переформулировать.",
                "actions": [],
                "metadata": {"error": str(e)},
                "should_save_to_rag": False
            }
