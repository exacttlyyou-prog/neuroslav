"""
Агент для обработки встреч.
"""
from typing import Dict, Any, List
from loguru import logger

from app.services.agents.base_agent import BaseAgent
from app.workflows.meeting_workflow import MeetingWorkflow
from app.models.schemas import IntentClassification


class MeetingAgent(BaseAgent):
    """Агент для обработки встреч."""
    
    def __init__(self):
        super().__init__()
        self.meeting_workflow = MeetingWorkflow()
    
    def get_agent_type(self) -> str:
        return "meeting"
    
    async def _process_with_context(
        self,
        user_input: str,
        classification: IntentClassification,
        context: List[str],
        sender_username: str = None
    ) -> Dict[str, Any]:
        """
        Обрабатывает встречу с контекстом из RAG.
        """
        try:
            # Проверяем, есть ли специальная команда "обработать последнюю встречу"
            if "последн" in user_input.lower() or "last" in user_input.lower():
                # Ищем последнюю встречу в Notion через API (без браузера)
                from app.services.notion_service import NotionService
                notion = NotionService()
                
                logger.info("🔍 Поиск последней встречи в Notion...")
                last_page = await notion.get_last_created_page()
                
                transcript = ""
                notion_page_id = None
                
                if last_page:
                    transcript = last_page.get("content", "")
                    notion_page_id = last_page.get("id")
                    logger.info(f"✅ Найдена последняя встреча в Notion: {last_page.get('title')}")
                else:
                    logger.warning("⚠️ Не найдена последняя встреча в Notion")
                    return {
                        "response": "Не удалось найти последнюю встречу в Notion. Убедитесь, что запись была завершена и сохранена.",
                        "actions": [],
                        "metadata": {},
                        "should_save_to_rag": False
                    }
                
                if transcript:
                    # Обрабатываем полученную встречу с контекстом из RAG и передачей username
                    workflow_result = await self.meeting_workflow.process_meeting(
                        transcript=transcript,
                        notion_page_id=notion_page_id,
                        sender_username=sender_username
                    )
                    # Контекст из RAG используется внутри MeetingWorkflow через RAG.search_similar_meetings
                    
                    # Формируем ответ через персону
                    meeting_id = workflow_result.get("meeting_id")
                    summary = workflow_result.get("summary", "")
                    telegram_sent = workflow_result.get("telegram_sent")
                    
                    context_info = f"""
                    Встреча обработана.
                    ID: {meeting_id}
                    Саммари: {summary[:200]}...
                    Отправлено в Telegram: {'Да' if telegram_sent and (telegram_sent.get("ok_message_id") or telegram_sent.get("admin_message_id")) else 'Нет'}
                    """
                    
                    response_text = await self.ollama.generate_persona_response(
                        user_input=f"Обработай последнюю встречу: {user_input}",
                        context=context_info
                    )
                    
                    # Добавляем технические детали если нужно
                    if not telegram_sent or (not telegram_sent.get("ok_message_id") and not telegram_sent.get("admin_message_id")):
                         response_text += f"\n\n(Техническое: отправь вручную через `POST /api/meetings/{meeting_id}/send`)"
                    
                    return {
                        "response": response_text,
                        "actions": [
                            {
                                "type": "meeting_processed",
                                "meeting_id": meeting_id,
                                "notion_page_id": workflow_result.get("metadata", {}).get("notion_page_id"),
                                "telegram_sent": bool(telegram_sent and (telegram_sent.get("ok_message_id") or telegram_sent.get("admin_message_id")))
                            }
                        ],
                        "metadata": {
                            "meeting_id": meeting_id,
                            "participants": workflow_result.get("participants", []),
                            "action_items": workflow_result.get("action_items", []),
                            "action_items_count": len(workflow_result.get("action_items", [])),
                            "telegram_sent": telegram_sent
                        },
                        "should_save_to_rag": True
                    }
            
            # Обычная обработка встречи (если передан transcript)
            # В этом случае user_input должен содержать транскрипт
            workflow_result = await self.meeting_workflow.process_meeting(
                transcript=user_input,
                sender_username=sender_username
            )
            
            # Формируем ответ через персону
            meeting_id = workflow_result.get("meeting_id")
            summary = workflow_result.get("summary", "")
            telegram_sent = workflow_result.get("telegram_sent")
            
            context_info = f"""
            Встреча обработана (из текста).
            ID: {meeting_id}
            Саммари: {summary[:200]}...
            Отправлено в Telegram: {'Да' if telegram_sent and (telegram_sent.get("ok_message_id") or telegram_sent.get("admin_message_id")) else 'Нет'}
            """
            
            response_text = await self.ollama.generate_persona_response(
                user_input=f"Обработай встречу из текста: {user_input[:50]}...",
                context=context_info
            )
            
            # Добавляем технические детали если нужно
            if not telegram_sent or (not telegram_sent.get("ok_message_id") and not telegram_sent.get("admin_message_id")):
                 response_text += f"\n\n(Техническое: отправь вручную через `POST /api/meetings/{meeting_id}/send`)"
            
            return {
                "response": response_text,
                "actions": [
                    {
                        "type": "meeting_processed",
                        "meeting_id": meeting_id,
                        "telegram_sent": bool(telegram_sent and (telegram_sent.get("ok_message_id") or telegram_sent.get("admin_message_id")))
                    }
                ],
                "metadata": {
                    "meeting_id": meeting_id,
                    "participants": workflow_result.get("participants", []),
                    "action_items": workflow_result.get("action_items", []),
                    "action_items_count": len(workflow_result.get("action_items", [])),
                    "telegram_sent": telegram_sent
                },
                "should_save_to_rag": True
            }
            
        except Exception as e:
            logger.error(f"Ошибка в MeetingAgent: {e}")
            return {
                "response": f"❌ Ошибка при обработке встречи: {str(e)}",
                "actions": [],
                "metadata": {"error": str(e)},
                "should_save_to_rag": False
            }
    
    def get_next_agents(self, result: Dict[str, Any]) -> List[str]:
        """
        Определяет, какие агенты должны работать после обработки встречи.
        
        После обработки встречи автоматически создаем задачи из action_items.
        """
        action_items = result.get("metadata", {}).get("action_items", [])
        if action_items and len(action_items) > 0:
            # Если есть задачи, запускаем TaskAgent для их создания
            return ["task"]
        return []
    
    async def _save_to_rag(self, user_input: str, result: Dict[str, Any]) -> None:
        """Сохраняет встречу в RAG."""
        try:
            meeting_id = result.get("metadata", {}).get("meeting_id")
            if meeting_id:
                # Встреча уже сохранена в RAG через MeetingWorkflow
                logger.debug(f"Встреча {meeting_id} уже сохранена в RAG через workflow")
        except Exception as e:
            logger.warning(f"Ошибка при сохранении встречи в RAG: {e}")
