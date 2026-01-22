"""
Webhook для обработки входящих сообщений от Telegram.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from pydantic import BaseModel

from app.services.daily_checkin_service import DailyCheckinService
from app.db.database import get_db

router = APIRouter()


class TelegramUpdate(BaseModel):
    """Модель обновления от Telegram."""
    update_id: int
    message: dict | None = None


@router.post("/webhook")
async def telegram_webhook(
    update: TelegramUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Обрабатывает входящие сообщения от Telegram.
    """
    try:
        if not update.message:
            return {"ok": True}
        
        message = update.message
        chat_id = str(message.get("chat", {}).get("id"))
        text = message.get("text", "")
        
        if not text:
            return {"ok": True}
        
        # Проверяем, является ли это ответом на ежедневный опрос
        # (можно добавить проверку по контексту или специальному маркеру)
        service = DailyCheckinService()
        clarification = await service.process_response(chat_id, text, db)
        
        if clarification:
            # Отправляем уточняющий вопрос
            await service.telegram.send_message_to_user(
                chat_id=chat_id,
                message=clarification
            )
        
        return {"ok": True}
    except Exception as e:
        logger.error(f"Ошибка при обработке webhook: {e}")
        # Все равно возвращаем ok, чтобы Telegram не повторял запрос
        return {"ok": True}
