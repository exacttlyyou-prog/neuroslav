"""
Агент для обработки задач.
"""
from typing import Dict, Any, List
from loguru import logger

from app.services.agents.base_agent import BaseAgent
from app.services.ollama_service import OllamaService
from app.workflows.task_workflow import TaskWorkflow
from app.models.schemas import IntentClassification


class TaskAgent(BaseAgent):
    """Агент для обработки задач."""
    
    def __init__(self):
        super().__init__()
        self.ollama = OllamaService(context_loader=self.context_loader)
        self.task_workflow = TaskWorkflow()
    
    def get_agent_type(self) -> str:
        return "task"
    
    async def _process_with_context(
        self,
        user_input: str,
        classification: IntentClassification,
        context: List[str]
    ) -> Dict[str, Any]:
        """
        Обрабатывает задачу с контекстом из RAG.
        """
        try:
            # Используем извлеченные данные из классификации или извлекаем заново
            extracted_data = classification.extracted_data
            
            # Если нет deadline в extracted_data, извлекаем через LLM
            # Используем контекст из RAG для улучшения извлечения
            if not extracted_data.get("deadline"):
                # Добавляем контекст похожих задач к промпту
                context_text = ""
                if context:
                    context_text = "\n\nПохожие задачи из истории:\n" + "\n".join([f"- {c[:100]}..." for c in context[:2]])
                
                task_intent = await self.ollama.extract_task_intent(user_input + context_text)
                extracted_data.update(task_intent)
            
            # Обрабатываем через TaskWorkflow
            task_text = extracted_data.get("intent") or user_input
            result = await self.task_workflow.process_task(
                task_text=task_text,
                create_in_notion=extracted_data.get("create_in_notion", False)
            )
            
            return {
                "response": f"✅ Задача создана: {result.get('task_id', 'N/A')}\n\n{result.get('message', '')}",
                "actions": [
                    {
                        "type": "task_created",
                        "task_id": result.get("task_id"),
                        "deadline": result.get("deadline"),
                        "priority": result.get("priority")
                    }
                ],
                "metadata": {
                    "task_id": result.get("task_id"),
                    "deadline": result.get("deadline"),
                    "priority": result.get("priority")
                },
                "should_save_to_rag": True
            }
            
        except Exception as e:
            logger.error(f"Ошибка в TaskAgent: {e}")
            return {
                "response": f"❌ Ошибка при создании задачи: {str(e)}",
                "actions": [],
                "metadata": {"error": str(e)},
                "should_save_to_rag": False
            }
    
    async def _save_to_rag(self, user_input: str, result: Dict[str, Any]) -> None:
        """Сохраняет задачу в RAG."""
        try:
            task_id = result.get("metadata", {}).get("task_id")
            if task_id:
                await self.rag.add_task(
                    task_id=task_id,
                    content=user_input,
                    metadata=result.get("metadata", {})
                )
        except Exception as e:
            logger.warning(f"Ошибка при сохранении задачи в RAG: {e}")
