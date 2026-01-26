"""
Агент для сохранения знаний.
"""
from typing import Dict, Any, List
from loguru import logger
import uuid

from app.services.agents.base_agent import BaseAgent
from app.workflows.knowledge_workflow import KnowledgeWorkflow
from app.models.schemas import IntentClassification


class KnowledgeAgent(BaseAgent):
    """Агент для сохранения информации в базу знаний."""
    
    def __init__(self):
        super().__init__()
        self.knowledge_workflow = KnowledgeWorkflow()
    
    def get_agent_type(self) -> str:
        return "knowledge"
    
    async def _process_with_context(
        self,
        user_input: str,
        classification: IntentClassification,
        context: List[str],
        sender_username: str = None
    ) -> Dict[str, Any]:
        """
        Сохраняет информацию в базу знаний.
        """
        try:
            # Извлекаем ключевые слова и категорию из extracted_data
            extracted_data = classification.extracted_data
            category = extracted_data.get("category", "general")
            keywords = extracted_data.get("keywords", [])
            
            # Сохраняем в RAG напрямую (для текстовой информации)
            doc_id = f"knowledge-{uuid.uuid4()}"
            await self.rag.add_knowledge(
                doc_id=doc_id,
                content=user_input,
                metadata={
                    "category": category,
                    "keywords": keywords,
                    "source": "chat"
                }
            )
            
            # Формируем ответ через персону
            context_info = f"""
            Информация сохранена в базу знаний.
            ID: {doc_id}
            Категория: {category}
            Ключевые слова: {', '.join(keywords) if keywords else 'нет'}
            """
            
            response_text = await self.ollama.generate_persona_response(
                user_input=f"Сохрани знание: {user_input}",
                context=context_info
            )
            
            return {
                "response": response_text,
                "actions": [
                    {
                        "type": "knowledge_saved",
                        "doc_id": doc_id,
                        "category": category
                    }
                ],
                "metadata": {
                    "doc_id": doc_id,
                    "category": category,
                    "keywords": keywords
                },
                "should_save_to_rag": False  # Уже сохранено выше
            }
            
        except Exception as e:
            logger.error(f"Ошибка в KnowledgeAgent: {e}")
            return {
                "response": f"❌ Ошибка при сохранении в базу знаний: {str(e)}",
                "actions": [],
                "metadata": {"error": str(e)},
                "should_save_to_rag": False
            }
