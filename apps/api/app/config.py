"""
Конфигурация приложения через переменные окружения.
API ключи только через переменные окружения.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    """Настройки приложения."""
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else ".env",
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )
    
    # Ollama (Local AI)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_max_tokens: int = 4096
    ollama_temperature: float = 0.7
    
    # ChromaDB (RAG)
    chroma_persist_dir: str = "./data/vector_db"
    
    # Notion (опционально для разработки)
    notion_token: str | None = None
    notion_mcp_token: str | None = None
    notion_meeting_page_id: str | None = None
    notion_people_db_id: str | None = None
    notion_projects_db_id: str | None = None
    notion_glossary_db_id: str | None = None
    notion_webhook_secret: str | None = None  # Для валидации подписи вебхуков
    
    # Telegram (опционально для разработки)
    telegram_bot_token: str | None = None
    admin_chat_id: str | None = None
    ok_chat_id: str | None = None
    
    # Telegram MCP (для MTProto серверов)
    telegram_api_id: str | None = None
    telegram_api_hash: str | None = None
    
    # Database
    database_url: str = "sqlite:///./data/digital_twin.db"
    
    # API
    api_port: int = 8000
    api_host: str = "0.0.0.0"


@lru_cache()
def get_settings() -> Settings:
    """Получить настройки (кэшировано)."""
    return Settings()
