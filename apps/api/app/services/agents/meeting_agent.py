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
        context: List[str]
    ) -> Dict[str, Any]:
        """
        Обрабатывает встречу с контекстом из RAG.
        """
        try:
            # Проверяем, есть ли специальная команда "обработать последнюю встречу"
            if "последн" in user_input.lower() or "last" in user_input.lower():
                # Используем автоматическую обработку через Playwright
                from app.services.notion_playwright_service import NotionPlaywrightService
                playwright = NotionPlaywrightService()
                result = await playwright.get_last_meeting_via_browser()
                
                if result.get("content"):
                    # Обрабатываем полученную встречу с контекстом из RAG
                    # Контекст уже получен в BaseAgent и передан в _process_with_context
                    workflow_result = await self.meeting_workflow.process_meeting(
                        transcript=result.get("content", ""),
                        notion_page_id=None
                    )
                    # Контекст из RAG используется внутри MeetingWorkflow через RAG.search_similar_meetings
                    
                    # Формируем ответ с информацией о встрече
                    meeting_id = workflow_result.get("meeting_id")
                    summary = workflow_result.get("summary", "")
                    telegram_sent = workflow_result.get("telegram_sent")
                    
                    response_parts = [
                        f"✅ Встреча обработана\n\n",
                        f"{summary[:500]}{'...' if len(summary) > 500 else ''}\n\n"
                    ]
                    
                    # Проверяем, было ли отправлено в Telegram
                    if telegram_sent:
                        ok_msg = telegram_sent.get("ok_message_id")
                        admin_msg = telegram_sent.get("admin_message_id")
                        if ok_msg or admin_msg:
                            response_parts.append("📤 Саммари отправлено в Telegram\n")
                        else:
                            response_parts.append("⚠️ Не удалось отправить в Telegram автоматически\n")
                    else:
                        response_parts.append("⚠️ Саммари не отправлено в Telegram\n")
                    
                    # Добавляем предложение отправить вручную, если не отправилось
                    if not telegram_sent or (not telegram_sent.get("ok_message_id") and not telegram_sent.get("admin_message_id")):
                        response_parts.append(f"\n💡 Чтобы отправить вручную, используйте:\n")
                        response_parts.append(f"`POST /api/meetings/{meeting_id}/send`\n")
                        response_parts.append(f"или команду в чате: `Отправь встречу {meeting_id}`")
                    
                    return {
                        "response": "".join(response_parts),
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
                            "action_items_count": len(workflow_result.get("action_items", [])),
                            "telegram_sent": telegram_sent
                        },
                        "should_save_to_rag": True
                    }
            
            # Обычная обработка встречи (если передан transcript)
            # В этом случае user_input должен содержать транскрипт
            workflow_result = await self.meeting_workflow.process_meeting(
                transcript=user_input
            )
            
            # Формируем ответ с информацией о встрече
            meeting_id = workflow_result.get("meeting_id")
            summary = workflow_result.get("summary", "")
            telegram_sent = workflow_result.get("telegram_sent")
            
            response_parts = [
                f"✅ Встреча обработана\n\n",
                f"{summary[:500]}{'...' if len(summary) > 500 else ''}\n\n"
            ]
            
            # Проверяем, было ли отправлено в Telegram
            if telegram_sent:
                ok_msg = telegram_sent.get("ok_message_id")
                admin_msg = telegram_sent.get("admin_message_id")
                if ok_msg or admin_msg:
                    response_parts.append("📤 Саммари отправлено в Telegram\n")
                else:
                    response_parts.append("⚠️ Не удалось отправить в Telegram автоматически\n")
            else:
                response_parts.append("⚠️ Саммари не отправлено в Telegram\n")
            
            # Добавляем предложение отправить вручную, если не отправилось
            if not telegram_sent or (not telegram_sent.get("ok_message_id") and not telegram_sent.get("admin_message_id")):
                response_parts.append(f"\n💡 Чтобы отправить вручную, используйте:\n")
                response_parts.append(f"`POST /api/meetings/{meeting_id}/send`\n")
                response_parts.append(f"или команду в чате: `Отправь встречу {meeting_id}`")
            
            return {
                "response": "".join(response_parts),
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
    
    async def _save_to_rag(self, user_input: str, result: Dict[str, Any]) -> None:
        """Сохраняет встречу в RAG."""
        try:
            meeting_id = result.get("metadata", {}).get("meeting_id")
            if meeting_id:
                # Встреча уже сохранена в RAG через MeetingWorkflow
                logger.debug(f"Встреча {meeting_id} уже сохранена в RAG через workflow")
        except Exception as e:
            logger.warning(f"Ошибка при сохранении встречи в RAG: {e}")
