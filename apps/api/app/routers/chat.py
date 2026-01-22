"""
API роутер для чата с агентами.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Optional
from loguru import logger
from pydantic import BaseModel

from app.services.agent_router import AgentRouter
from app.models.schemas import AgentResponse

router = APIRouter()


class ChatMessage(BaseModel):
    """Сообщение в чате."""
    role: str  # "user" или "assistant"
    content: str
    agent_type: Optional[str] = None
    metadata: Optional[dict] = None


class ChatRequest(BaseModel):
    """Запрос к чату."""
    message: str
    history: Optional[List[ChatMessage]] = None


class ChatResponse(BaseModel):
    """Ответ от чата."""
    agent_type: str
    response: str
    actions: List[dict]
    metadata: dict


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Обрабатывает сообщение пользователя через агентов.
    
    Args:
        request: Запрос с сообщением и историей
        
    Returns:
        Ответ от агента
    """
    try:
        router_service = AgentRouter()
        
        # Классифицируем сообщение
        logger.info(f"Классификация сообщения: {request.message[:100]}...")
        classification = await router_service.classify(request.message)
        
        # Маршрутизируем к агенту
        logger.info(f"Маршрутизация к агенту: {classification.agent_type}")
        response = await router_service.route(request.message, classification)
        
        return ChatResponse(
            agent_type=response.agent_type,
            response=response.response,
            actions=response.actions,
            metadata=response.metadata
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения в чате: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health():
    """Health check для чата."""
    return {"status": "ok", "service": "chat"}
