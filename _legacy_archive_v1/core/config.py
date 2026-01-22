"""
Конфигурация приложения через переменные окружения.
API ключи только через переменные окружения.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Настройки приложения."""
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        # Безопасность: не читать из других источников
        extra='ignore'
    )
    
    # Ollama (Local AI)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"  # Модель Ollama (по умолчанию qwen3:8b, можно переопределить через OLLAMA_MODEL)
    ollama_max_tokens: int = 4096
    ollama_temperature: float = 0.7
    
    # ChromaDB (RAG)
    chroma_persist_dir: str = "./db"
    
    # Notion
    notion_token: str  # Только из переменных окружения
    notion_mcp_token: str | None = None  # OAuth токен для remote MCP сервера Notion
    notion_meeting_page_id: str | None = None  # ID страницы для чтения встреч (опционально для скриптов)
    notion_people_db_id: str | None = None  # ID базы данных "Люди"
    notion_projects_db_id: str | None = None  # ID базы данных "Проекты"
    notion_glossary_db_id: str | None = None  # ID базы данных "Глоссарий"
    
    # Telegram
    telegram_bot_token: str  # Только из переменных окружения
    admin_chat_id: str  # ID чата админа для уведомлений


@lru_cache()
def get_settings() -> Settings:
    """Получить настройки (кэшировано)."""
    return Settings()

