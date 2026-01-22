# Digital Twin API (FastAPI Backend)

Backend для системы Digital Twin - обработка задач, встреч и документов с использованием Ollama и Notion.

## Технологии

- FastAPI
- Ollama (локальный LLM)
- Notion API
- ChromaDB (векторная БД)
- SQLite
- Telegram Bot API

## Установка

```bash
# Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # или .venv\Scripts\activate на Windows

# Установить зависимости
pip install -r requirements.txt
```

## Настройка

Создайте файл `.env` в корне проекта (или скопируйте из `.env.example`):

```env
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b

# Notion
NOTION_TOKEN=secret_...
NOTION_PEOPLE_DB_ID=...
NOTION_PROJECTS_DB_ID=...
NOTION_MEETING_PAGE_ID=...

# Telegram
TELEGRAM_BOT_TOKEN=...
ADMIN_CHAT_ID=...

# ChromaDB
CHROMA_PERSIST_DIR=./data/vector_db

# Database
DATABASE_URL=sqlite:///./data/digital_twin.db
```

## Запуск

```bash
# Активировать виртуальное окружение
source .venv/bin/activate

# Запустить сервер
uvicorn app.main:app --reload --port 8000
```

API будет доступен по адресу: http://localhost:8000

## API Endpoints

### Tasks
- `POST /api/tasks` - Создать задачу
- `GET /api/tasks` - Список задач
- `GET /api/tasks/{id}` - Получить задачу
- `PUT /api/tasks/{id}` - Обновить задачу
- `DELETE /api/tasks/{id}` - Удалить задачу

### Meetings
- `POST /api/meetings/process` - Обработать встречу
- `GET /api/meetings` - Список встреч
- `GET /api/meetings/{id}` - Получить встречу
- `POST /api/meetings/{id}/send` - Отправить draft через Telegram

### Knowledge
- `POST /api/knowledge/index` - Индексировать документ
- `GET /api/knowledge/search?q=query` - Поиск по знаниям
- `GET /api/knowledge` - Список документов

## Структура

```
apps/api/
├── app/
│   ├── main.py              # FastAPI приложение
│   ├── config.py            # Настройки
│   ├── routers/             # API endpoints
│   ├── services/             # Бизнес-логика
│   ├── workflows/            # Workflows обработки
│   ├── models/               # Pydantic схемы
│   └── db/                   # База данных
├── data/                     # Данные (БД, векторная БД)
└── requirements.txt
```

## Требования

- Python 3.11+
- Ollama должен быть запущен (http://localhost:11434)
- Notion интеграция настроена
- Telegram Bot создан
