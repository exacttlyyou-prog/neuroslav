"""Интеграции агента AI Project Manager."""
# Ленивые импорты, чтобы не ломать при отсутствии опциональных зависимостей
try:
    from .gemini_client import GeminiClient
except ImportError:
    GeminiClient = None

try:
    from .notion_client import NotionTaskCreator
except ImportError:
    NotionTaskCreator = None

try:
    from .telegram_client import TelegramClient
except ImportError:
    TelegramClient = None

try:
    from .firestore_client import FirestoreClient
except ImportError:
    FirestoreClient = None

try:
    from .calendar_scheduler import CalendarScheduler
except ImportError:
    CalendarScheduler = None

__all__ = [
    'GeminiClient',
    'NotionTaskCreator',
    'TelegramClient',
    'FirestoreClient',
    'CalendarScheduler',
]

