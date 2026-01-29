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


@router.get("/summary")
async def get_daily_summary(
    checkin_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Получить сводный отчет по daily check-in за день.
    
    Args:
        checkin_date: Дата в формате YYYY-MM-DD (по умолчанию сегодня)
    """
    try:
        from datetime import datetime, timedelta
        from app.services.ollama_service import OllamaService
        
        # Определяем дату
        if checkin_date:
            target_date = datetime.fromisoformat(checkin_date).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            target_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Получаем все ответы за день
        result = await db.execute(
            select(DailyCheckin, Contact)
            .join(Contact, DailyCheckin.contact_id == Contact.id)
            .where(DailyCheckin.checkin_date == target_date)
        )
        checkins_with_contacts = result.all()
        
        if not checkins_with_contacts:
            return {
                "date": target_date.strftime('%Y-%m-%d'),
                "total_sent": 0,
                "total_responded": 0,
                "summary": "Нет данных за этот день",
                "by_status": {},
                "responses": []
            }
        
        # Подсчитываем статистику
        total_sent = len(checkins_with_contacts)
        total_responded = sum(1 for c, _ in checkins_with_contacts if c.status in ["responded", "completed"])
        
        # Группируем по статусам (если есть категоризация в Notion)
        by_status = {
            "Выполнено": 0,
            "В процессе": 0,
            "Проблема": 0,
            "Не ответил": 0
        }
        
        responses = []
        all_responses_text = []
        
        for checkin, contact in checkins_with_contacts:
            response_data = {
                "name": contact.name,
                "response": checkin.response_text or "Нет ответа",
                "status": checkin.status,
                "response_time": checkin.response_received_at.isoformat() if checkin.response_received_at else None
            }
            responses.append(response_data)
            
            if checkin.status == "completed" and checkin.response_text:
                all_responses_text.append(f"{contact.name}: {checkin.response_text[:200]}")
            elif checkin.status in ["sent", "pending"]:
                by_status["Не ответил"] += 1
        
        # Генерируем сводку через Ollama
        summary_text = "Нет ответов"
        if all_responses_text:
            try:
                ollama = OllamaService()
                summary_prompt = f"""Сделай краткую сводку по ежедневным отчетам команды за {target_date.strftime('%d.%m.%Y')}:

Ответы сотрудников:
{chr(10).join(all_responses_text[:20])}

Сделай краткую сводку (3-5 предложений):
- Кто что сделал
- Основные достижения
- Проблемы или блокеры (если есть)
- Общий статус команды

Стиль: кратко, по делу, без воды."""
                
                summary_response = await ollama.client.chat(
                    model=ollama.model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": "Ты делаешь сводки по ежедневным отчетам команды. Кратко, по делу."
                        },
                        {
                            "role": "user",
                            "content": summary_prompt
                        }
                    ],
                    options={
                        "temperature": 0.5,
                        "num_predict": 300
                    }
                )
                
                if hasattr(summary_response, 'message') and hasattr(summary_response.message, 'content'):
                    summary_text = summary_response.message.content.strip()
                elif isinstance(summary_response, dict):
                    summary_text = summary_response.get('message', {}).get('content', '').strip()
                else:
                    summary_text = str(summary_response).strip()
                    
            except Exception as e:
                logger.error(f"Ошибка при генерации сводки: {e}")
                summary_text = f"Получено {total_responded} ответов из {total_sent} отправленных"
        
        return {
            "date": target_date.strftime('%Y-%m-%d'),
            "total_sent": total_sent,
            "total_responded": total_responded,
            "response_rate": round(total_responded / total_sent * 100, 1) if total_sent > 0 else 0,
            "summary": summary_text,
            "by_status": by_status,
            "responses": responses
        }
        
    except Exception as e:
        logger.error(f"Ошибка при получении сводки: {e}")
        raise HTTPException(status_code=500, detail=str(e))
