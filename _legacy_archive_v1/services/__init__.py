"""Сервисы локального бота."""
from .notion_service import NotionService
from .telegram_service import TelegramService
from .calendar_service import CalendarService

__all__ = [
    'NotionService',
    'TelegramService',
    'CalendarService',
]

