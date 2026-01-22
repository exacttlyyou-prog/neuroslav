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
        self.ollama = OllamaService(context_loader=self.context_loader)
    
    def get_agent_type(self) -> str:
        return "default"
    
    async def _process_with_context(
        self,
        user_input: str,
        classification: IntentClassification,
        context: List[str]
    ) -> Dict[str, Any]:
        """
        Обрабатывает общий запрос или вопрос.
        """
        try:
            # Используем LLM для генерации ответа
            prompt = f"""Ты — Нейрослав, цифровой двойник Вячеслава.
Отвечай кратко и по делу. Если вопрос не относится к задачам, встречам или знаниям, дай краткий ответ.

Вопрос: {user_input}

Ответ:"""
            
            response_text = await self.ollama.summarize_text(prompt, max_length=300)
            
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
