"""
API роутер для встреч.
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from loguru import logger

from app.workflows.meeting_workflow import MeetingWorkflow
from app.db.models import Meeting
from app.db.database import get_db
from app.services.recording_service import get_recording_service

router = APIRouter()


@router.post("/process")
async def process_meeting(
    transcript: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None),
    notion_page_id: Optional[str] = Form(None)
):
    """
    Обрабатывает встречу через Meeting Workflow.
    
    Args:
        transcript: Текст транскрипта (опционально)
        audio_file: Аудио файл (опционально)
        notion_page_id: ID страницы Notion (опционально)
        
    Returns:
        Результат обработки встречи
    """
    try:
        audio_content = None
        if audio_file:
            audio_content = await audio_file.read()
        
        if not transcript and not audio_content:
            raise HTTPException(status_code=400, detail="Необходим transcript или audio_file")
        
        workflow = MeetingWorkflow()
        result = await workflow.process_meeting(
            transcript=transcript,
            audio_file=audio_content,
            notion_page_id=notion_page_id
        )
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при обработке встречи: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def get_meetings(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> List[dict]:
    """
    Получает список встреч.
    
    Args:
        status: Фильтр по статусу (опционально)
        
    Returns:
        Список встреч
    """
    try:
        from sqlalchemy import desc
        query = select(Meeting).order_by(desc(Meeting.created_at))
        if status:
            query = query.where(Meeting.status == status)
        
        result = await db.execute(query)
        meetings = result.scalars().all()
        
        return [
            {
                "id": meeting.id,
                "summary": meeting.summary,
                "participants": meeting.participants,
                "projects": meeting.projects,
                "action_items": meeting.action_items,
                "key_decisions": meeting.key_decisions,
                "insights": meeting.insights,
                "next_steps": meeting.next_steps,
                "status": meeting.status,
                "created_at": meeting.created_at.isoformat() if meeting.created_at else None
            }
            for meeting in meetings
        ]
    except Exception as e:
        logger.error(f"Ошибка при получении встреч: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{meeting_id}")
async def get_meeting(meeting_id: str, db: AsyncSession = Depends(get_db)):
    """Получает встречу по ID."""
    try:
        result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = result.scalar_one_or_none()
        
        if not meeting:
            raise HTTPException(status_code=404, detail="Встреча не найдена")
        
        return {
            "id": meeting.id,
            "transcript": meeting.transcript,
            "summary": meeting.summary,
            "participants": meeting.participants,
            "projects": meeting.projects,
            "action_items": meeting.action_items,
            "key_decisions": getattr(meeting, 'key_decisions', None),
            "insights": getattr(meeting, 'insights', None),
            "next_steps": getattr(meeting, 'next_steps', None),
            "draft_message": meeting.draft_message,
            "status": meeting.status,
            "created_at": meeting.created_at.isoformat() if meeting.created_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении встречи: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{meeting_id}/send")
async def send_meeting_draft(meeting_id: str, db: AsyncSession = Depends(get_db)):
    """Отправляет draft follow-up сообщения через Telegram."""
    try:
        result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = result.scalar_one_or_none()
        
        if not meeting:
            raise HTTPException(status_code=404, detail="Встреча не найдена")
        
        if not meeting.draft_message:
            raise HTTPException(status_code=400, detail="Draft сообщение отсутствует")
        
        from app.services.telegram_service import TelegramService
        telegram = TelegramService()
        message_id = await telegram.send_meeting_draft(meeting.draft_message)
        
        # Обновляем статус
        meeting.status = "sent"
        await db.commit()
        
        return {
            "message_id": message_id,
            "message": "Draft сообщение отправлено"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при отправке draft: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{meeting_id}/approve-and-send")
async def approve_and_send_meeting(
    meeting_id: str,
    summary: Optional[str] = Form(None),
    participants: Optional[str] = Form(None),  # JSON строка
    action_items: Optional[str] = Form(None),  # JSON строка
    key_decisions: Optional[str] = Form(None),  # JSON строка
    insights: Optional[str] = Form(None),  # JSON строка
    next_steps: Optional[str] = Form(None),  # JSON строка
    db: AsyncSession = Depends(get_db)
):
    """
    Отправляет саммари встречи в Telegram после согласования и редактирования.
    
    Args:
        meeting_id: ID встречи
        summary: Отредактированное саммари (опционально, если не указано - используется оригинальное)
        participants: Отредактированный список участников в формате JSON (опционально)
        action_items: Отредактированный список задач в формате JSON (опционально)
    """
    import json
    
    try:
        result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = result.scalar_one_or_none()
        
        if not meeting:
            raise HTTPException(status_code=404, detail="Встреча не найдена")
        
        if meeting.status != "pending_approval":
            raise HTTPException(
                status_code=400, 
                detail=f"Встреча не ожидает согласования. Текущий статус: {meeting.status}"
            )
        
        # Используем отредактированные данные или оригинальные
        final_summary = summary if summary else meeting.summary
        final_participants = json.loads(participants) if participants else (meeting.participants or [])
        final_action_items = json.loads(action_items) if action_items else (meeting.action_items or [])
        final_key_decisions = json.loads(key_decisions) if key_decisions else (meeting.key_decisions or [])
        final_insights = json.loads(insights) if insights else (meeting.insights or [])
        final_next_steps = json.loads(next_steps) if next_steps else (meeting.next_steps or [])
        
        # Отправляем в Telegram
        from app.services.telegram_service import TelegramService
        from app.config import get_settings
        
        telegram = TelegramService()
        settings = get_settings()
        send_to_ok = bool(settings.ok_chat_id)
        
        telegram_result = await telegram.send_meeting_summary(
            summary=final_summary,
            action_items=final_action_items,
            participants=final_participants,
            send_to_ok=send_to_ok,
            send_to_admin=True
        )
        
        # Обновляем данные встречи (если были изменения)
        if summary:
            meeting.summary = final_summary
        if participants:
            meeting.participants = final_participants
        if action_items:
            meeting.action_items = final_action_items
        if key_decisions:
            meeting.key_decisions = final_key_decisions
        if insights:
            meeting.insights = final_insights
        if next_steps:
            meeting.next_steps = final_next_steps
        
        # Обновляем статус
        meeting.status = "sent"
        await db.commit()
        
        logger.info(f"Встреча {meeting_id} отправлена в Telegram после согласования")
        
        return {
            "meeting_id": meeting_id,
            "telegram_sent": telegram_result,
            "message": "Саммари встречи отправлено в Telegram"
        }
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Неверный формат JSON: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при отправке встречи после согласования: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_recording():
    """
    Запускает запись встречи.
    
    Returns:
        Статус запуска записи
    """
    try:
        recording_service = get_recording_service()
        success = recording_service.start_recording()
        
        if success:
            return {
                "status": "started",
                "message": "Запись встречи запущена"
            }
        else:
            raise HTTPException(
                status_code=409,
                detail="Запись уже идет или не удалось запустить"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при запуске записи: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_recording():
    """
    Останавливает запись встречи.
    
    Returns:
        Статус остановки записи
    """
    try:
        recording_service = get_recording_service()
        success = await recording_service.stop_recording()
        
        if success:
            return {
                "status": "stopped",
                "message": "Запись встречи остановлена"
            }
        else:
            raise HTTPException(
                status_code=409,
                detail="Запись не запущена"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при остановке записи: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_recording_status():
    """
    Получает статус записи встречи.
    
    Returns:
        Статус записи
    """
    try:
        recording_service = get_recording_service()
        status = recording_service.get_status()
        
        return status
    except Exception as e:
        logger.error(f"Ошибка при получении статуса записи: {e}")
        raise HTTPException(status_code=500, detail=str(e))
