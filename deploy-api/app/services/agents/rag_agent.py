"""
Агент для поиска по базе знаний (RAG).
"""
from typing import Dict, Any, List
from loguru import logger

from app.services.agents.base_agent import BaseAgent
from app.services.ollama_service import OllamaService
from app.models.schemas import IntentClassification


class RAGAgent(BaseAgent):
    """Агент для поиска информации в базе знаний."""
    
    def __init__(self):
        super().__init__()
        # self.ollama уже инициализирован в BaseAgent
    
    def get_agent_type(self) -> str:
        return "rag_query"
    
    async def _process_with_context(
        self,
        user_input: str,
        classification: IntentClassification,
        context: List[str],
        sender_username: str = None,
        sender_chat_id: str = None
    ) -> Dict[str, Any]:
        """
        Ищет информацию в базе знаний и формирует ответ.
        """
        try:
            # Ищем в разных коллекциях RAG
            results = []
            
            # Поиск в встречах
            meetings = await self.rag.search_similar_meetings(user_input, limit=3)
            if meetings:
                results.append({
                    "type": "meetings",
                    "items": meetings
                })
            
            # Поиск в знаниях
            knowledge = await self.rag.search_knowledge(user_input, limit=3)
            if knowledge:
                results.append({
                    "type": "knowledge",
                    "items": knowledge
                })
            
            # Поиск в задачах
            tasks = await self.rag.search_similar_tasks(user_input, limit=3)
            if tasks:
                results.append({
                    "type": "tasks",
                    "items": tasks
                })
            
            # Формируем контекст из найденной информации
            context_text = ""
            if results:
                for result_group in results:
                    if result_group["type"] == "meetings":
                        context_text += "\n📅 ВСТРЕЧИ:\n"
                        for item in result_group["items"][:2]:
                            content = item.get("content", "")[:500] if isinstance(item, dict) else str(item)[:500]
                            context_text += f"- {content}...\n"
                    
                    elif result_group["type"] == "knowledge":
                        context_text += "\n📚 ЗНАНИЯ:\n"
                        for item in result_group["items"][:2]:
                            content = item.get("content", "")[:500] if isinstance(item, dict) else str(item)[:500]
                            context_text += f"- {content}...\n"
                    
                    elif result_group["type"] == "tasks":
                        context_text += "\n✅ ЗАДАЧИ:\n"
                        for item in result_group["items"][:2]:
                            content = item.get("content", "")[:500] if isinstance(item, dict) else str(item)[:500]
                            context_text += f"- {content}...\n"
            else:
                context_text = "Информации в базе не найдено."

            # Генерируем ответ через персону Neural Slav
            response_text = await self.ollama.generate_persona_response(
                user_input=user_input,
                context=context_text
            )
            
            return {
                "response": response_text,
                "actions": [
                    {
                        "type": "rag_search",
                        "results_count": sum(len(r["items"]) for r in results)
                    }
                ],
                "metadata": {
                    "results": results,
                    "query": user_input
                },
                "should_save_to_rag": False
            }
            
        except Exception as e:
            logger.error(f"Ошибка в RAGAgent: {e}")
            return {
                "response": f"❌ Ошибка при поиске: {str(e)}",
                "actions": [],
                "metadata": {"error": str(e)},
                "should_save_to_rag": False
            }
