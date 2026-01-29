"""
Агент для обработки задач.
"""
from typing import Dict, Any, List
from datetime import datetime
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
    
    def get_next_agents(self, result: Dict[str, Any]) -> List[str]:
        """
        Определяет, какие агенты должны работать после создания задачи.
        
        После создания задачи проверяем связанные проекты через KnowledgeAgent.
        """
        project = result.get("metadata", {}).get("project")
        if project:
            # Если есть проект, обновляем знания о нем
            return ["knowledge"]
        return []
    
    async def _process_with_context(
        self,
        user_input: str,
        classification: IntentClassification,
        context: List[str],
        sender_username: str = None,
        sender_chat_id: str = None
    ) -> Dict[str, Any]:
        """
        Обрабатывает задачу с контекстом из RAG.
        """
        try:
            # Проверяем, пришли ли задачи из цепочки (от MeetingAgent)
            extracted_data = classification.extracted_data
            action_items = extracted_data.get("action_items", [])
            
            # Если есть action_items из цепочки, создаем задачи для каждой
            if action_items and isinstance(action_items, list):
                created_tasks = []
                for item in action_items:
                    if isinstance(item, dict):
                        task_text = item.get("text", "")
                        assignee = item.get("assignee", "")
                        deadline = item.get("deadline")
                        priority = item.get("priority", "Medium")
                        
                        if task_text:
                            # Формируем текст задачи с контекстом
                            task_full_text = task_text
                            if assignee:
                                task_full_text += f" (ответственный: {assignee})"
                            if deadline:
                                task_full_text += f" (дедлайн: {deadline})"
                            
                            # Создаем задачу
                            task_result = await self.task_workflow.process_task(
                                task_text=task_full_text,
                                create_in_notion=True
                            )
                            created_tasks.append({
                                "task_id": task_result.get("task_id"),
                                "text": task_text,
                                "assignee": assignee,
                                "deadline": deadline,
                                "priority": priority
                            })
                
                if created_tasks:
                    response_text = await self.ollama.generate_persona_response(
                        user_input=f"Создано {len(created_tasks)} задач из встречи",
                        context=f"Задачи созданы: {', '.join([t['text'][:50] for t in created_tasks])}"
                    )
                    
                    return {
                        "response": response_text,
                        "actions": [
                            {
                                "type": "tasks_created_from_meeting",
                                "tasks": created_tasks
                            }
                        ],
                        "metadata": {
                            "tasks_created": len(created_tasks),
                            "tasks": created_tasks
                        },
                        "should_save_to_rag": True
                    }
            
            # Обычная обработка задачи (если не из цепочки)
            # Используем извлеченные данные из классификации или извлекаем заново
            if not extracted_data.get("deadline"):
                # Добавляем контекст похожих задач к промпту
                context_text = ""
                if context:
                    context_text = "\n\nПохожие задачи из истории:\n" + "\n".join([f"- {c[:100]}..." for c in context[:2]])
                
                task_intent = await self.ollama.extract_task_intent(user_input + context_text)
                extracted_data.update(task_intent)
            
            # Улучшенная обработка дедлайна с помощью DateParserService
            deadline_raw = extracted_data.get("deadline")
            if deadline_raw:
                from app.services.date_parser_service import get_date_parser_service
                date_parser = get_date_parser_service()
                
                # Если дедлайн уже в формате datetime, оставляем как есть
                if isinstance(deadline_raw, str):
                    parsed_deadline = date_parser.parse_datetime(deadline_raw)
                    if parsed_deadline:
                        extracted_data["deadline"] = parsed_deadline.isoformat()
                        logger.info(f"Дедлайн '{deadline_raw}' распарсен как {parsed_deadline}")
                    else:
                        # Если не удалось распарсить, пробуем найти дедлайн в тексте задачи
                        fallback_deadline = date_parser.parse_deadline(user_input)
                        if fallback_deadline:
                            extracted_data["deadline"] = fallback_deadline.isoformat()
                            logger.info(f"Использован дедлайн по умолчанию: {fallback_deadline}")
            else:
                # Если дедлайн не извлекся из LLM, пробуем найти его в тексте
                from app.services.date_parser_service import get_date_parser_service
                date_parser = get_date_parser_service()
                
                fallback_deadline = date_parser.parse_deadline(user_input, default_hours=48)  # 2 дня по умолчанию
                if fallback_deadline and (fallback_deadline - datetime.now()).total_seconds() > 3600:  # Не менее часа
                    extracted_data["deadline"] = fallback_deadline.isoformat()
                    logger.info(f"Автоматически определен дедлайн: {fallback_deadline}")
            
            # Обрабатываем через TaskWorkflow
            task_text = extracted_data.get("intent") or user_input
            result = await self.task_workflow.process_task(
                task_text=task_text,
                create_in_notion=extracted_data.get("create_in_notion", False)
            )
            
            # Формируем информативный ответ через персону
            context_info = f"""
            Задача создана успешно.
            ID: {result.get('task_id', 'N/A')}
            Ответственный: {result.get('assignee', 'Не назначен')}
            Проект: {result.get('project', 'Не указан')}
            Дедлайн: {result.get('deadline', 'Не указан')}
            Приоритет: {result.get('priority', 'Medium')}
            """
            
            response_text = await self.ollama.generate_persona_response(
                user_input=user_input,
                context=context_info
            )
            
            return {
                "response": response_text,
                "actions": [
                    {
                        "type": "task_created",
                        "task_id": result.get("task_id"),
                        "deadline": result.get("deadline"),
                        "priority": result.get("priority"),
                        "assignee": result.get("assignee"),
                        "project": result.get("project")
                    }
                ],
                "metadata": {
                    "task_id": result.get("task_id"),
                    "deadline": result.get("deadline"),
                    "priority": result.get("priority"),
                    "assignee": result.get("assignee"),
                    "project": result.get("project")
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
