"""
API роутер для формирования отчетов.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any
from loguru import logger

from app.routers.daily_checkin import get_daily_summary
from app.db.database import get_db

router = APIRouter()

@router.get("/daily")
async def get_daily_report(
    date: Optional[str] = Query(None, description="Дата отчета в формате YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Получить сводный отчет по работе команды за день.
    """
    try:
        # Переиспользуем логику из daily_checkin роутера
        return await get_daily_summary(checkin_date=date, db=db)
    except Exception as e:
        logger.error(f"Ошибка при формировании ежедневного отчета: {e}")
        raise HTTPException(status_code=500, detail=str(e))
