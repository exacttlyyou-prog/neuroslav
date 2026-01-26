"""
Pytest конфигурация и фикстуры для тестов.
"""
import pytest
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.database import get_db, Base
from app.config import get_settings


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Создает event loop для всей сессии тестов."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Создает временную тестовую базу данных."""
    # Используем in-memory SQLite для тестов
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False
    )
    
    # Создаем все таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Создаем сессию
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with AsyncSessionLocal() as session:
        yield session
    
    await engine.dispose()


@pytest.fixture
def test_client(test_db: AsyncSession) -> TestClient:
    """Создает тестовый клиент FastAPI."""
    
    # Переопределяем зависимость базы данных
    async def override_get_db():
        yield test_db
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as client:
        yield client
    
    # Очищаем переопределения
    app.dependency_overrides.clear()


@pytest.fixture
def mock_ollama_service():
    """Мокает OllamaService для тестов."""
    mock = AsyncMock()
    
    # Настройка стандартных ответов
    mock.generate_persona_response.return_value = "Тестовый ответ в стиле Neural Slav"
    mock.analyze_meeting.return_value = {
        "summary_md": "Тестовое саммари встречи",
        "participants": [{"name": "Тестовый участник"}],
        "action_items": [],
        "key_decisions": [],
        "insights": [],
        "next_steps": [],
        "projects": [],
        "meeting_date": None,
        "meeting_time": None,
        "risk_assessment": ""
    }
    mock.summarize_text.return_value = "Тестовый суммари"
    
    return mock


@pytest.fixture
def mock_notion_service():
    """Мокает NotionService для тестов."""
    mock = AsyncMock()
    
    # Настройка стандартных ответов
    mock.validate_token.return_value = True
    mock.ensure_required_databases.return_value = {
        "people_db": "exists",
        "projects_db": "exists", 
        "meetings_db": "created",
        "tasks_db": "created",
        "errors": []
    }
    mock.get_contacts_from_db.return_value = [
        {
            "id": "test-id",
            "name": "Тестовый Пользователь",
            "telegram_username": "testuser",
            "role": "Developer",
            "context": "Тестовый контекст",
            "aliases": ["тест", "test"]
        }
    ]
    mock.get_projects_from_db.return_value = [
        {
            "name": "Тестовый Проект",
            "key": "TEST",
            "description": "Тестовое описание",
            "status": "Active",
            "keywords": ["test", "тест"]
        }
    ]
    mock.create_meeting_in_db.return_value = {
        "id": "test-meeting-id",
        "url": "https://notion.so/test-meeting"
    }
    
    return mock


@pytest.fixture
def mock_telegram_service():
    """Мокает TelegramService для тестов."""
    mock = AsyncMock()
    
    # Настройка стандартных ответов
    mock.validate_token.return_value = True
    mock.send_message_to_user.return_value = {
        "message_id": 123,
        "chat_id": "test_chat",
        "success": True
    }
    mock.edit_message.return_value = True
    
    return mock


@pytest.fixture
def mock_rag_service():
    """Мокает RAGService для тестов."""
    mock = AsyncMock()
    
    # Настройка стандартных ответов
    mock.search_similar_meetings.return_value = [
        {
            "content": "Тестовый контент встречи",
            "metadata": {"meeting_id": "test-meeting"}
        }
    ]
    mock.search_knowledge.return_value = [
        {
            "content": "Тестовый контент знаний", 
            "metadata": {"source": "test"}
        }
    ]
    mock.add_meeting.return_value = True
    mock.add_knowledge.return_value = True
    
    return mock


@pytest.fixture
def mock_context_loader():
    """Мокает ContextLoader для тестов."""
    mock = MagicMock()
    
    # Настройка стандартных данных
    mock.people = {
        "testuser": {
            "name": "Тестовый Пользователь",
            "role": "Developer", 
            "context": "Тестовый контекст",
            "telegram_username": "testuser",
            "aliases": ["тест", "test"],
            "source": "test"
        }
    }
    
    mock.projects = [
        {
            "name": "Тестовый Проект",
            "key": "TEST",
            "description": "Тестовое описание", 
            "status": "Active",
            "keywords": ["test", "тест"],
            "source": "test"
        }
    ]
    
    mock.glossary = {
        "тест": "Проверочный процесс",
        "API": "Application Programming Interface"
    }
    
    # Настройка методов
    mock.find_people_in_text.return_value = [mock.people["testuser"]]
    mock.find_projects_in_text.return_value = [mock.projects[0]]
    mock.get_person_context.return_value = "Developer: Тестовый контекст"
    mock.resolve_entity = AsyncMock(return_value=mock.people["testuser"])
    mock.ensure_notion_sync = AsyncMock()
    
    return mock


@pytest.fixture
def sample_telegram_update():
    """Создает образец Telegram update для тестов."""
    return {
        "update_id": 123456789,
        "message": {
            "message_id": 123,
            "date": 1640995200,
            "chat": {
                "id": 12345,
                "type": "private"
            },
            "from": {
                "id": 12345,
                "is_bot": False,
                "first_name": "Test",
                "username": "testuser",
                "language_code": "ru"
            },
            "text": "Тестовое сообщение"
        }
    }


@pytest.fixture
def sample_meeting_transcript():
    """Создает образец транскрипции встречи для тестов."""
    return """
    Участники встречи: Иван Петров, Мария Сидорова
    
    Иван: Давайте обсудим проект TEST. Нужно сделать презентацию к пятнице.
    Мария: Хорошо, я займусь этим. Также нужно обновить документацию.
    Иван: Отлично. Ещё один вопрос - когда запускаем в продакшн?
    Мария: Думаю, на следующей неделе будем готовы.
    
    Решили:
    1. Мария делает презентацию к пятнице
    2. Обновить документацию
    3. Запуск в продакшн на следующей неделе
    """


# Настройка для всех тестов
@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Автоматически настраивает тестовое окружение для всех тестов."""
    # Отключаем внешние сервисы
    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test:telegram-token")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")