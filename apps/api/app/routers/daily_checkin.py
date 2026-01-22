"""
API роутер для ежедневных опросов.
"""
from fastapi import APIRouter, HTTPException, Depends, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from loguru import logger
from pydantic import BaseModel

from app.services.daily_checkin_service import DailyCheckinService
from app.db.models import DailyCheckin, Contact
from app.db.database import get_db

router = APIRouter()


class SendDailyQuestionsResponse(BaseModel):
    sent: int
    failed: int


@router.post("/send")
async def send_daily_questions(
    db: AsyncSession = Depends(get_db)
) -> SendDailyQuestionsResponse:
    """
    Отправить ежедневные вопросы всем членам команды.
    """
    try:
        service = DailyCheckinService()
        results = await service.send_daily_questions(db)
        return SendDailyQuestionsResponse(**results)
    except Exception as e:
        logger.error(f"Ошибка при отправке еженедельных вопросов: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process-response")
async def process_response(
    chat_id: str = Body(...),
    response_text: str = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Обработать ответ на ежедневный опрос.
    """
    try:
        service = DailyCheckinService()
        clarification = await service.process_response(chat_id, response_text, db)
        
        if clarification:
            # Отправляем уточняющий вопрос
            await service.telegram.send_message_to_user(
                chat_id=chat_id,
                message=clarification
            )
            return {"clarification_sent": True, "message": clarification}
        
        return {"clarification_sent": False}
    except Exception as e:
        logger.error(f"Ошибка при обработке ответа: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def get_checkins(
    checkin_date: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> List[dict]:
    """
    Получить список ежедневных опросов.
    """
    try:
        query = select(DailyCheckin).join(Contact, DailyCheckin.contact_id == Contact.id)
        
        if checkin_date:
            from datetime import datetime
            checkin_date_dt = datetime.fromisoformat(checkin_date)
            query = query.where(DailyCheckin.checkin_date == checkin_date_dt)
        
        if status:
            query = query.where(DailyCheckin.status == status)
        
        result = await db.execute(query)
        checkins = result.scalars().all()
        
        return [
            {
                "id": checkin.id,
                "contact_id": checkin.contact_id,
                "checkin_date": checkin.checkin_date.isoformat() if checkin.checkin_date else None,
                "question_sent_at": checkin.question_sent_at.isoformat() if checkin.question_sent_at else None,
                "response_received_at": checkin.response_received_at.isoformat() if checkin.response_received_at else None,
                "response_text": checkin.response_text,
                "clarification_asked": checkin.clarification_asked,
                "status": checkin.status,
                "created_at": checkin.created_at.isoformat() if checkin.created_at else None
            }
            for checkin in checkins
        ]
    except Exception as e:
        logger.error(f"Ошибка при получении опросов: {e}")
        raise HTTPException(status_code=500, detail=str(e))
