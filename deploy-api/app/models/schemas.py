"""
Pydantic схемы для валидации данных.
"""
from pydantic import BaseModel, Field, ConfigDict, validator
from datetime import datetime
from typing import List, Literal, Optional, Dict, Any, Union
from uuid import UUID
import re


class ActionItem(BaseModel):
    """Задача из встречи."""
    model_config = ConfigDict(strict=True)
    
    text: str = Field(description="Четкая, выполнимая формулировка задачи")
    assignee: Optional[str] = Field(default=None, description="Имя ответственного (точно как упомянуто в тексте) или None")
    deadline: Optional[str] = Field(default=None, description="Дедлайн задачи в формате YYYY-MM-DD или относительная дата (завтра, через неделю, к пятнице)")
    priority: Literal['High', 'Medium', 'Low'] = Field(description="Приоритет задачи на основе контекста")


class Participant(BaseModel):
    """Участник встречи."""
    model_config = ConfigDict(strict=True)
    
    name: str = Field(description="Имя участника (точно как упомянуто в тексте)")
    role: Optional[str] = Field(default=None, description="Роль или должность участника, если упомянута")


class KeyDecision(BaseModel):
    """Ключевое решение, принятое на встрече."""
    model_config = ConfigDict(strict=True)
    
    title: str = Field(description="Краткое название решения")
    description: str = Field(description="Подробное описание решения и его обоснование")
    impact: Optional[str] = Field(default=None, description="Влияние решения на проект/команду")


class MeetingAnalysis(BaseModel):
    """Результат анализа встречи."""
    model_config = ConfigDict(strict=True)
    
    summary_md: str = Field(description="Расширенное саммари в формате Markdown для Telegram (HTML теги: <b>, <i>, <blockquote>). Должно быть 7-10 предложений с деталями встречи, ключевыми моментами и контекстом")
    key_decisions: List[KeyDecision] = Field(default_factory=list, description="Список ключевых решений, принятых на встрече. Извлекай все важные решения, которые влияют на проект или команду")
    insights: List[str] = Field(default_factory=list, description="Список инсайтов и важных наблюдений из встречи. Это могут быть паттерны, тренды, неожиданные открытия")
    next_steps: List[str] = Field(default_factory=list, description="Следующие шаги и планы (кроме конкретных action_items). Общие направления развития, стратегические шаги")
    participants: List[Participant] = Field(default_factory=list, description="Список всех участников встречи (обязательно извлеки всех упомянутых людей)")
    action_items: List[ActionItem] = Field(default_factory=list, description="Список всех задач с четкими формулировками, дедлайнами и ответственными")
    projects: List[str] = Field(default_factory=list, description="Список упомянутых проектов (используй ключи проектов из KNOWN ENTITIES, если они есть)")
    meeting_date: Optional[str] = Field(default=None, description="Дата встречи в формате YYYY-MM-DD (если упомянута в тексте)")
    meeting_time: Optional[str] = Field(default=None, description="Время встречи в формате HH:MM (если упомянуто)")
    risk_assessment: str = Field(default="", description="Краткая оценка рисков, если есть (оставь пустым, если рисков нет)")


class TaskExtraction(BaseModel):
    """Извлеченная информация о задаче."""
    model_config = ConfigDict(strict=True)
    
    intent: str = Field(description="Четкая, выполнимая формулировка задачи (что именно нужно сделать)")
    deadline: Optional[str] = Field(default=None, description="Дедлайн в формате YYYY-MM-DD или относительная дата (завтра, через неделю, к пятнице, до конца месяца)")
    priority: Literal['High', 'Medium', 'Low'] = Field(description="Приоритет задачи на основе срочности и важности")
    assignee: Optional[str] = Field(default=None, description="Имя ответственного (точно как упомянуто в тексте) или null")
    project: Optional[str] = Field(default=None, description="Ключ проекта из KNOWN ENTITIES (если упомянут) или null")


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


class SecureTelegramUpdate(BaseModel):
    """Валидированная модель Telegram update с проверками безопасности."""
    model_config = ConfigDict(strict=True, extra="ignore")  # extra: Telegram может слать edited_message и др.
    
    update_id: int = Field(gt=0, description="Положительный ID обновления")
    message: Optional[Dict[str, Any]] = Field(None, description="Сообщение Telegram")
    callback_query: Optional[Dict[str, Any]] = Field(None, description="Callback query от inline кнопок")
    
    @validator('message')
    def validate_message_security(cls, v):
        """Валидация сообщения на предмет безопасности."""
        if not v:
            return v
        
        # Проверяем размер сообщения
        if isinstance(v.get('text'), str) and len(v['text']) > 10000:
            raise ValueError("Сообщение слишком длинное (>10000 символов)")
        
        # Проверяем chat_id
        chat_info = v.get('chat', {})
        if not isinstance(chat_info.get('id'), int):
            raise ValueError("Некорректный chat ID")
        
        # Проверяем на подозрительные паттерны
        text = v.get('text', '')
        if isinstance(text, str):
            # Проверка на потенциальные SQL инъекции
            sql_patterns = [
                r"(?i)(union\s+select|drop\s+table|insert\s+into|delete\s+from)",
                r"(?i)(script\s*>|javascript:|vbscript:)",
                r"[<>\"'&\x00-\x1f\x7f-\x9f]{10,}",  # Подозрительные символы подряд
            ]
            
            for pattern in sql_patterns:
                if re.search(pattern, text):
                    from loguru import logger
                    logger.warning(f"Подозрительный паттерн в сообщении: {pattern}")
                    # Не блокируем, но логируем
        
        return v


class SecureTextInput(BaseModel):
    """Безопасная модель для текстового ввода."""
    model_config = ConfigDict(strict=True)
    
    text: str = Field(min_length=1, max_length=5000, description="Текст сообщения")
    source: Optional[str] = Field(None, max_length=100, description="Источник сообщения")
    
    @validator('text')
    def sanitize_text(cls, v):
        """Санитизация текстового ввода."""
        if not isinstance(v, str):
            raise ValueError("Текст должен быть строкой")
        
        # Убираем потенциально опасные символы
        # Разрешаем только базовые символы
        sanitized = re.sub(r'[<>"\'\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', v)
        
        # Проверяем на скрипты
        script_patterns = [
            r"(?i)javascript:",
            r"(?i)vbscript:",
            r"(?i)on\w+\s*=",  # onclick, onload и т.д.
        ]
        
        for pattern in script_patterns:
            if re.search(pattern, sanitized):
                raise ValueError("Обнаружен потенциально опасный код")
        
        return sanitized.strip()


class UserIdentity(BaseModel):
    """Модель для идентификации пользователя."""
    model_config = ConfigDict(strict=True)
    
    chat_id: str = Field(min_length=1, max_length=50, description="Telegram Chat ID")
    username: Optional[str] = Field(None, max_length=100, description="Telegram username")
    first_name: Optional[str] = Field(None, max_length=100, description="Имя")
    last_name: Optional[str] = Field(None, max_length=100, description="Фамилия")
    
    @validator('username')
    def validate_username(cls, v):
        """Валидация username."""
        if v and not re.match(r'^[a-zA-Z0-9_]{1,32}$', v):
            raise ValueError("Некорректный формат username")
        return v
    
    @validator('chat_id')
    def validate_chat_id(cls, v):
        """Валидация chat_id."""
        if not v or not v.strip():
            raise ValueError("Chat ID не может быть пустым")
        
        # Проверяем что это похоже на Telegram chat_id
        if not re.match(r'^-?\d+$', v.strip()):
            raise ValueError("Chat ID должен быть числом")
        
        return v.strip()


class RateLimitInfo(BaseModel):
    """Информация о лимитах запросов."""
    model_config = ConfigDict(strict=True)
    
    requests_remaining: int = Field(ge=0, description="Оставшееся количество запросов")
    requests_per_minute: int = Field(gt=0, description="Лимит запросов в минуту")
    reset_time: datetime = Field(description="Время сброса лимита")
    client_id: str = Field(description="Идентификатор клиента")


class SecurityEvent(BaseModel):
    """Модель события безопасности."""
    model_config = ConfigDict(strict=True)
    
    event_type: str = Field(description="Тип события")
    severity: str = Field(description="Критичность")
    client_id: str = Field(description="Идентификатор клиента")
    description: str = Field(description="Описание события") 
    timestamp: datetime = Field(default_factory=datetime.now)
    context: Dict[str, Any] = Field(default_factory=dict, description="Контекст события")
