"""
Конфигурация приложения через переменные окружения.
API ключи только через переменные окружения.
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
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
    ollama_timeout_sec: int = 90  # Таймаут запроса к Ollama (генерация может быть долгой)
    
    # ChromaDB (RAG)
    chroma_persist_dir: str = "./data/vector_db"
    
    # Notion (опционально для разработки)
    notion_token: str | None = None
    notion_mcp_token: str | None = None
    notion_ai_context_page_id: str | None = None  # Основная страница AI Context — всё хранится внутри неё. Приоритет над notion_meeting_page_id
    notion_meeting_page_id: str | None = None  # Fallback: корень, под которым ищут/создают AI Context, встречи, задачи (если не задан notion_ai_context_page_id)
    notion_meeting_minutes_page_id: str | None = None  # Опционально: если не указана, создается автоматически
    notion_tasks_page_id: str | None = None  # Если задана — задачи из бота пишутся сюда (append block), иначе — дочерняя страница meeting_page_id
    notion_people_db_id: str | None = None
    notion_projects_db_id: str | None = None
    notion_glossary_db_id: str | None = None
    notion_webhook_secret: str | None = None  # Для валидации подписи вебхуков
    
    # Telegram (опционально для разработки)
    telegram_bot_token: str | None = None
    admin_chat_id: str | None = None
    ok_chat_id: str | None = None
    telegram_webhook_url: str | None = None  # URL для автоматической настройки webhook при старте
    
    # Telegram MCP (для MTProto серверов)
    telegram_api_id: str | None = None
    telegram_api_hash: str | None = None
    
    # Database (на Vercel ./data недоступна для записи — используем /tmp)
    database_url: str = Field(
        default_factory=lambda: "sqlite:////tmp/digital_twin.db" if os.environ.get("VERCEL") == "1" else "sqlite:///./data/digital_twin.db"
    )
    
    # API
    api_port: int = 8000
    api_host: str = "0.0.0.0"

    @model_validator(mode="after")
    def vercel_db_path(self):
        """На Vercel принудительно /tmp для SQLite (./data недоступна)."""
        if os.environ.get("VERCEL") != "1":
            return self
        url = getattr(self, "database_url", "") or ""
        if "data/digital_twin" in url or url.startswith("sqlite:///./"):
            object.__setattr__(self, "database_url", "sqlite:////tmp/digital_twin.db")
        return self


@lru_cache()
def get_settings() -> Settings:
    """Получить настройки (кэшировано)."""
    return Settings()
