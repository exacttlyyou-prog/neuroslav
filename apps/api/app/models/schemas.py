"""
Pydantic схемы для валидации данных.
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import List, Literal, Optional, Dict, Any
from uuid import UUID


class ActionItem(BaseModel):
    """Задача из встречи."""
    model_config = ConfigDict(strict=True)
    
    text: str = Field(description="Четкая, выполнимая формулировка задачи")
    assignee: Optional[str] = Field(default=None, description="Имя ответственного или None")
    priority: Literal['High', 'Medium', 'Low'] = Field(description="Приоритет задачи")


class MeetingAnalysis(BaseModel):
    """Результат анализа встречи."""
    model_config = ConfigDict(strict=True)
    
    summary_md: str = Field(description="Саммари в формате Markdown для Telegram")
    action_items: List[ActionItem] = Field(default_factory=list, description="Список задач")
    projects: List[str] = Field(default_factory=list, description="Список упомянутых проектов (ключи проектов из Notion)")
    meeting_date_proposal: Optional[datetime] = Field(default=None, description="Предложенная дата встречи")
    risk_assessment: str = Field(default="", description="Краткая оценка рисков, если есть")


class MessageClassification(BaseModel):
    """Классификация входящего сообщения."""
    model_config = ConfigDict(strict=True)
    
    type: Literal["task", "reminder", "knowledge"] = Field(description="Тип сообщения")
    summary: str = Field(description="Краткое саммари сообщения")
    datetime: Optional[str] = Field(default=None, description="Дата и время напоминания (если тип 'reminder')")
    action_needed: bool = Field(description="Требуется ли действие")


class IntentClassification(BaseModel):
    """Классификация намерения пользователя для роутинга к агенту."""
    model_config = ConfigDict(strict=True)
    
    agent_type: Literal["task", "meeting", "message", "knowledge", "rag_query", "default"] = Field(
        description="Тип агента для обработки"
    )
    confidence: float = Field(description="Уверенность классификации (0.0-1.0)")
    extracted_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Извлеченные данные из сообщения (deadline, участники, etc.)"
    )
    reasoning: str = Field(description="Объяснение классификации")


class AgentResponse(BaseModel):
    """Ответ агента после обработки."""
    model_config = ConfigDict(strict=True)
    
    agent_type: str = Field(description="Тип агента")
    response: str = Field(description="Текстовый ответ пользователю")
    actions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Действия, которые были выполнены (создана задача, отправлено сообщение, etc.)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Дополнительные метаданные (meeting_id, task_id, etc.)"
    )
