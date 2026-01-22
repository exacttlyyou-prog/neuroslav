# AI Project Manager - Архитектура

## Технологический стек (Local-First, 2026)

- **Runtime:** Python 3.12+ (AsyncIO)
- **Infrastructure:** Локальный сервер (Polling mode)
- **AI Model:** Ollama (локальный LLM: `llama3` или `mistral`)
- **RAG:** ChromaDB (локальная векторная БД) + sentence-transformers (`all-MiniLM-L6-v2`)
- **Data Validation:** Pydantic V2 (Strict Mode)
- **State & Logs:** In-memory state + loguru
- **Integrations:** Notion (async API + MCP), Telegram Bot API (polling)

## Архитектура (Local-First, Polling)

### Компоненты системы

#### 1. `main.py` - Telegram Bot (Polling)

**Режим работы:** Polling (локальный запуск)

**Основные функции:**
- `/start` - приветствие и список команд
- `/analyze` - анализ последней встречи из Notion
- `/refresh` - обновление контекста из Notion баз данных
- Обработка текстовых сообщений (классификация: task/reminder/knowledge)
- Обработка callback queries (Approve/Cancel)
- Обработка Reply сообщений (обновление черновиков)

**Процесс анализа встречи:**
1. Читает последнюю встречу из Notion через `get_latest_meeting_notes()`
2. Ищет похожие встречи в ChromaDB (RAG)
3. Анализирует через Ollama с контекстом (Sudo Slava persona)
4. Отправляет результат в Telegram с кнопками Approve/Cancel
5. При одобрении: создает задачи в Notion, сохраняет в ChromaDB

**Процесс обработки сообщений:**
1. Определяет автора (через ContactsService)
2. Классифицирует через Ollama (task/reminder/knowledge)
3. Action Router:
   - `knowledge` → сохраняет в ChromaDB
   - `task` → создает задачу в Notion
   - `reminder` → заглушка (в разработке)

#### 2. `main_watcher.py` - Автоматический мониторинг Notion

**Режим работы:** Polling loop (каждые 60 секунд)

**Процесс:**
1. При старте: читает последнюю запись, сохраняет её ID (без отправки)
2. В цикле: каждые 60 секунд проверяет новую запись
3. Если ID изменился: анализирует через AI, отправляет в Telegram
4. Обновляет `last_processed_block_id`

#### 3. `run_last_meeting.py` - One-Click Test

**Назначение:** Быстрое тестирование анализа последней встречи

**Процесс:**
1. Загружает последнюю встречу из Notion
2. Анализирует через Ollama
3. Отправляет результат в Telegram

### Сервисы

#### `core/ai_service.py` - OllamaClient

- **Методы:**
  - `analyze_meeting()` - анализ встречи с контекстом из RAG
  - `classify_message()` - классификация входящих сообщений
- **Особенности:**
  - Использует нативную библиотеку `ollama`
  - Поддержка fallback: `generate()` → `chat()`
  - Retry логика через `tenacity`
  - Интеграция с ContextLoader для обогащения промптов

#### `core/rag_service.py` - LocalRAG

- **Коллекции ChromaDB:**
  - `meetings` - одобренные анализы встреч
  - `knowledge` - знания из входящих сообщений
- **Методы:**
  - `search_similar()` - поиск похожих встреч по вектору
  - `save_approved()` - сохранение одобренного анализа
  - `save_knowledge()` - сохранение знаний из сообщений

#### `core/context_loader.py` - ContextLoader

- **Источники данных:**
  - Notion базы данных (People, Projects) - приоритет
  - JSON файлы (`data/people.json`, `data/projects.json`) - fallback
- **Функции:**
  - `sync_context_from_notion()` - синхронизация из Notion
  - `resolve_entity()` - умный поиск людей/проектов по алиасам
  - `get_person_context()` - получение контекста человека
  - `enrich_message_with_projects()` - обогащение промпта проектами

#### `services/notion_service.py` - NotionService

- **Методы:**
  - `get_latest_meeting_notes()` - получение последней встречи (MCP → fallback на обычный API)
  - `get_page_content()` - получение всего контента страницы
  - `create_tasks()` - создание задач в Notion
- **Особенности:**
  - Приоритет MCP Notion для чтения meeting-notes блоков
  - Fallback на обычный Notion API
  - Retry логика через `tenacity`

#### `core/contacts_service.py` - ContactsService

- **Источник:** `contacts.json`
- **Метод:** `resolve_user()` - разрешение пользователя Telegram по username/first_name

### Схемы данных (Pydantic V2 Strict Mode)

- `ActionItem`: задача с текстом, ответственным и приоритетом
- `MeetingAnalysis`: результат анализа (саммари в HTML, задачи, дата, риски)
- `MessageClassification`: классификация сообщения (type, summary, datetime, action_needed)
- `AnalysisSession`: сессия анализа (в памяти, не в БД)

### State Management

- **In-memory:** `pending_approvals` (dict) - временное хранение черновиков анализов
- **Persistent:** ChromaDB - долгосрочное хранение одобренных анализов и знаний

## Запуск

### Локальный запуск бота

```bash
# Установка зависимостей
pip install -r requirements.txt

# Настройка переменных окружения
cp .env.example .env
# Заполнить .env файл:
# - NOTION_TOKEN
# - TELEGRAM_BOT_TOKEN
# - ADMIN_CHAT_ID
# - NOTION_MEETING_PAGE_ID
# - NOTION_PEOPLE_DB_ID
# - NOTION_PROJECTS_DB_ID

# Запуск Ollama (если не запущен)
ollama serve

# Загрузка модели
ollama pull llama3

# Запуск бота
python main.py
```

### Автоматический мониторинг

```bash
python main_watcher.py
```

### Тестирование

```bash
python run_last_meeting.py
```

## Настройка

1. **Ollama:** Установить и запустить локально, загрузить модель (`llama3` или `mistral`)
2. **Notion:** Создать интеграцию, получить токен, расшарить страницы/базы данных
3. **Telegram:** Создать бота через @BotFather, получить токен и chat_id
4. **ChromaDB:** Автоматически создается в `./db` при первом запуске
5. **Context:** Настроить базы данных People и Projects в Notion (или использовать JSON fallback)

## Особенности

- **Local-First:** Все данные и AI обработка локально
- **MCP Notion:** Используется для чтения meeting-notes блоков (через инструменты Cursor)
- **RAG:** ChromaDB для поиска похожих встреч и накопления знаний
- **Persona:** "Sudo Slava" - сухой, циничный, конкретный стиль общения
- **Human-in-the-loop:** Одобрение анализов перед сохранением и созданием задач