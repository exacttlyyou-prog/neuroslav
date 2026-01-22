"""
Pydantic V2 модели для валидации данных агента AI Project Manager.
Strict Mode включен для строгой типизации.
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import List, Literal
from uuid import UUID


class ActionItem(BaseModel):
    """Элемент действия из анализа встречи."""
    model_config = ConfigDict(strict=True)
    
    text: str = Field(description="Четкая, выполнимая формулировка задачи")
    assignee: str | None = Field(default=None, description="Имя ответственного или None")
    priority: Literal['High', 'Medium', 'Low'] = Field(description="Приоритет задачи")


class MeetingAnalysis(BaseModel):
    """Результат анализа встречи от Gemini."""
    model_config = ConfigDict(strict=True)
    
    summary_md: str = Field(description="Саммари в формате Markdown для Telegram")
    action_items: List[ActionItem] = Field(default_factory=list, description="Список задач")
    meeting_date_proposal: datetime | None = Field(default=None, description="Предложенная дата встречи")
    risk_assessment: str = Field(default="", description="Краткая оценка рисков, если есть")


class AnalysisSession(BaseModel):
    """Сессия анализа (локальная, в памяти)."""
    model_config = ConfigDict(strict=True)
    
    session_id: UUID = Field(description="Уникальный ID сессии")
    notion_page_id: str = Field(description="ID страницы Notion")
    status: Literal['pending_approval', 'approved', 'executed', 'rejected'] = Field(
        default='pending_approval',
        description="Статус сессии"
    )
    analysis: MeetingAnalysis | None = Field(default=None, description="Результат анализа")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    telegram_message_id: int | None = Field(default=None, description="ID сообщения в Telegram")


class MessageClassification(BaseModel):
    """Классификация входящего сообщения."""
    model_config = ConfigDict(strict=True)
    
    type: Literal["task", "reminder", "knowledge"] = Field(description="Тип сообщения")
    summary: str = Field(description="Краткое саммари сообщения")
    datetime: str | None = Field(default=None, description="Дата и время для напоминания (YYYY-MM-DD HH:MM)")
    action_needed: bool = Field(description="Требуется ли действие")
