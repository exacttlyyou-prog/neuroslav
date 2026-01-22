"""
API роутер для задач.
"""
from fastapi import APIRouter, HTTPException, Depends, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from loguru import logger
from pydantic import BaseModel

from app.workflows.task_workflow import TaskWorkflow
from app.db.models import Task
from app.db.database import get_db

router = APIRouter()


class CreateTaskRequest(BaseModel):
    text: str
    create_in_notion: bool = False


@router.post("")
async def create_task(
    request: CreateTaskRequest
):
    """
    Создает задачу и обрабатывает её через Task Workflow.
    
    Args:
        text: Текст задачи
        create_in_notion: Создавать ли задачу в Notion
        
    Returns:
        Результат обработки задачи
    """
    try:
        workflow = TaskWorkflow()
        result = await workflow.process_task(request.text, create_in_notion=request.create_in_notion)
        return result
    except Exception as e:
        logger.error(f"Ошибка при создании задачи: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def get_tasks(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> List[dict]:
    """
    Получает список задач.
    
    Args:
        status: Фильтр по статусу (опционально)
        
    Returns:
        Список задач
    """
    try:
        query = select(Task)
        if status:
            query = query.where(Task.status == status)
        
        result = await db.execute(query)
        tasks = result.scalars().all()
        
        return [
            {
                "id": task.id,
                "text": task.text,
                "intent": task.intent,
                "deadline": task.deadline.isoformat() if task.deadline else None,
                "priority": task.priority,
                "status": task.status,
                "created_at": task.created_at.isoformat() if task.created_at else None
            }
            for task in tasks
        ]
    except Exception as e:
        logger.error(f"Ошибка при получении задач: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}")
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Получает задачу по ID."""
    try:
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        
        if not task:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        
        return {
            "id": task.id,
            "text": task.text,
            "intent": task.intent,
            "deadline": task.deadline.isoformat() if task.deadline else None,
            "priority": task.priority,
            "status": task.status,
            "created_at": task.created_at.isoformat() if task.created_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении задачи: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{task_id}")
async def update_task(
    task_id: str,
    status: str = None,
    db: AsyncSession = Depends(get_db)
):
    """Обновляет задачу."""
    try:
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        
        if not task:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        
        if status:
            task.status = status
        
        await db.commit()
        await db.refresh(task)
        
        return {
            "id": task.id,
            "status": task.status,
            "message": "Задача обновлена"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при обновлении задачи: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}")
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Удаляет задачу."""
    try:
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        
        if not task:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        
        await db.delete(task)
        await db.commit()
        
        return {"message": "Задача удалена"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении задачи: {e}")
        raise HTTPException(status_code=500, detail=str(e))
