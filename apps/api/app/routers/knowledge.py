"""
API роутер для знаний (RAG).
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from loguru import logger

from app.workflows.knowledge_workflow import KnowledgeWorkflow
from app.services.rag_service import RAGService
from app.db.models import KnowledgeItem
from app.db.database import get_db

router = APIRouter()


@router.post("/index")
async def index_document(
    file: UploadFile = File(...)
):
    """
    Индексирует документ через Knowledge Workflow.
    
    Args:
        file: Файл для индексации
        
    Returns:
        Результат индексации
    """
    try:
        file_content = await file.read()
        file_type = file.content_type or "application/octet-stream"
        
        workflow = KnowledgeWorkflow()
        result = await workflow.process_document(
            file_content=file_content,
            filename=file.filename,
            file_type=file_type
        )
        
        return result
    except Exception as e:
        logger.error(f"Ошибка при индексации документа: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_knowledge(
    q: str = Query(..., description="Поисковый запрос"),
    limit: int = Query(5, ge=1, le=20)
):
    """
    Ищет в базе знаний через RAG.
    
    Args:
        q: Поисковый запрос
        limit: Количество результатов
        
    Returns:
        Список релевантных документов
    """
    try:
        rag = RAGService()
        results = await rag.search_knowledge(query=q, limit=limit)
        
        return {
            "query": q,
            "results": results
        }
    except Exception as e:
        logger.error(f"Ошибка при поиске в базе знаний: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def get_knowledge_items(db: AsyncSession = Depends(get_db)) -> List[dict]:
    """
    Получает список индексированных документов.
    
    Returns:
        Список документов
    """
    try:
        result = await db.execute(select(KnowledgeItem))
        items = result.scalars().all()
        
        return [
            {
                "id": item.id,
                "source_file": item.source_file,
                "file_type": item.file_type,
                "chunks_count": item.chunks_count,
                "indexed_at": item.indexed_at.isoformat() if item.indexed_at else None
            }
            for item in items
        ]
    except Exception as e:
        logger.error(f"Ошибка при получении документов: {e}")
        raise HTTPException(status_code=500, detail=str(e))
