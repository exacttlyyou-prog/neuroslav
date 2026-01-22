"""Core модули локального бота."""
from .ai_service import OllamaClient
from .config import get_settings
from .context_loader import ContextLoader
from .rag_service import LocalRAG
from .contacts_service import ContactsService

__all__ = ['OllamaClient', 'get_settings', 'ContextLoader', 'LocalRAG', 'ContactsService']

