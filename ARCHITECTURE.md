# 🏗️ Digital Twin System - Architecture

## Обзор системы

Digital Twin — это система обработки персональных данных, которая превращает неструктурированный ввод (задачи, встречи, документы) в структурированные действия и знания.

---

## Архитектурные принципы

1. **Separation of Concerns**: Четкое разделение Frontend, Backend, Workflows
2. **Serverless-First**: Использование serverless функций где возможно
3. **Event-Driven**: Workflows запускаются асинхронно через очереди
4. **Type Safety**: TypeScript + Pydantic для типобезопасности
5. **Modularity**: Каждый workflow — независимый модуль

---

## Системная архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │  Tasks   │  │ Meetings │  │ Context  │                  │
│  │   Tab    │  │   Tab    │  │   Tab    │                  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                  │
│       │             │             │                          │
│       └─────────────┴─────────────┘                          │
│                    │                                          │
│              ┌─────▼─────┐                                    │
│              │ API Routes│                                    │
│              │ (Next.js) │                                    │
│              └─────┬─────┘                                    │
└────────────────────┼──────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
┌───────▼────┐ ┌─────▼─────┐ ┌──▼──────────┐
│  FastAPI   │ │  LangGraph │ │  Vector DB  │
│  Backend   │ │ Workflows  │ │ (ChromaDB)  │
└──────┬─────┘ └─────┬─────┘ └──────┬───────┘
       │             │              │
       └─────────────┴──────────────┘
                     │
       ┌─────────────┼─────────────┐
       │             │             │
┌──────▼────┐ ┌─────▼─────┐ ┌────▼─────┐
│   OpenAI  │ │  Telegram │ │  SQLite  │
│    API    │ │    Bot    │ │    DB    │
└───────────┘ └────────────┘ └──────────┘
```

---

## Компоненты системы

### 1. Frontend Layer (Next.js App Router)

#### Структура:
```
app/
├── (tabs)/              # Группа роутов с общим layout
│   ├── tasks/           # /tasks
│   ├── meetings/        # /meetings
│   └── context/         # /context
├── api/                 # API Routes
│   ├── tasks/
│   ├── meetings/
│   └── knowledge/
└── layout.tsx           # Root layout
```

#### Технологии:
- **Next.js 14+** с App Router для SSR и routing
- **React Server Components** для оптимизации
- **Shadcn/UI** для компонентов
- **Zustand** для client-side state
- **React Hook Form + Zod** для валидации форм

#### Ключевые компоненты:
- `TaskInputForm` — форма ввода задачи
- `MeetingUploadForm` — загрузка встречи
- `DocumentUploadForm` — загрузка документа
- `DraftPreview` — предпросмотр сгенерированного контента
- `TaskList` — список задач с фильтрами

---

### 2. Backend Layer

#### 2.1 Next.js API Routes (Serverless)

**Назначение**: Легкие endpoints для CRUD операций и оркестрации.

**Endpoints**:
```
POST   /api/tasks              # Создать задачу
GET    /api/tasks              # Список задач
PUT    /api/tasks/:id          # Обновить задачу
DELETE /api/tasks/:id          # Удалить задачу

POST   /api/meetings/process    # Обработать встречу
GET    /api/meetings/:id        # Получить результат

POST   /api/knowledge/index     # Индексировать документ
GET    /api/knowledge/search    # Поиск по знаниям
```

**Преимущества**:
- Нет необходимости в отдельном сервере
- Автоматическое масштабирование на Vercel
- Простая интеграция с Frontend

#### 2.2 FastAPI Backend (Опционально)

**Назначение**: Тяжелые AI workflows, которые требуют долгой обработки.

**Структура**:
```
app/
├── main.py              # FastAPI app
├── routers/
│   ├── workflows.py     # Endpoints для workflows
│   └── health.py       # Health check
├── workflows/           # LangGraph workflows
│   ├── meeting_workflow.py
│   ├── task_workflow.py
│   └── knowledge_workflow.py
└── services/
    ├── llm_service.py
    ├── vector_db.py
    └── notification_service.py
```

**Когда использовать**:
- Сложные async workflows
- Интеграция с Python-библиотеками (LangChain, transformers)
- Долгая обработка (> 30 сек)

---

### 3. Workflow Layer (LangGraph)

#### Workflow A: Meeting Processing

```python
# Псевдокод структуры
MeetingWorkflow:
  1. Extract Transcript (if audio → Whisper)
  2. Summarize (LLM: GPT-4o)
  3. Extract Participants (NER)
  4. Match Contacts (Fuzzy matching)
  5. Generate Draft (LLM: GPT-4o)
  6. Store Result (DB)
  7. Return to Frontend
```

**Входные данные**:
- Аудио файл (MP3, WAV) или текст транскрипта

**Выходные данные**:
- Summary встречи
- Список участников (с матчингом к контактам)
- Draft follow-up сообщения

**Интеграции**:
- OpenAI Whisper API (аудио → текст)
- OpenAI GPT-4o (суммаризация, генерация)
- Contacts DB (матчинг)

---

#### Workflow B: Task Processing

```python
TaskWorkflow:
  1. Parse Intent (LLM: GPT-4o-mini)
  2. Extract Deadline (LLM + date parser)
  3. Calculate Absolute Date ("next tuesday" → 2025-01-28)
  4. Store Task (DB)
  5. Schedule Notification (Task Queue)
  6. Return Confirmation
```

**Входные данные**:
- Текст задачи (например: "Напомни мне про встречу в следующий вторник")

**Выходные данные**:
- Структурированная задача (title, deadline, status)
- Подтверждение сохранения

**Интеграции**:
- OpenAI GPT-4o-mini (быстрый и дешевый для простых задач)
- Date parser (dateutil или custom)
- Task Queue (BullMQ или встроенный scheduler)

---

#### Workflow C: Knowledge Indexing

```python
KnowledgeWorkflow:
  1. Upload Document (PDF/PPTX/DOCX)
  2. Extract Text (PyPDF2, python-pptx, python-docx)
  3. Extract Images (if PPTX/PDF with images)
  4. Analyze Images (GPT-4o-vision)
  5. Chunk Text (LangChain text splitter)
  6. Generate Embeddings (OpenAI embeddings)
  7. Index to Vector DB (ChromaDB/Pinecone)
  8. Store Metadata (SQLite)
  9. Return Success
```

**Входные данные**:
- Файл (PDF, PPTX, DOCX)

**Выходные данные**:
- Подтверждение индексации
- Количество чанков

**Интеграции**:
- OpenAI GPT-4o-vision (анализ изображений)
- OpenAI embeddings (векторизация)
- Vector DB (ChromaDB/Pinecone)

---

### 4. Data Layer

#### 4.1 SQLite Database (Development)

**Таблицы**:
```sql
-- Задачи
CREATE TABLE tasks (
  id TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  deadline DATE,
  status TEXT, -- pending, scheduled, completed
  created_at TIMESTAMP,
  notified_at TIMESTAMP
);

-- Встречи
CREATE TABLE meetings (
  id TEXT PRIMARY KEY,
  transcript TEXT,
  summary TEXT,
  participants JSON, -- [{name, contact_id}]
  draft_message TEXT,
  status TEXT, -- processing, completed, sent
  created_at TIMESTAMP
);

-- Знания
CREATE TABLE knowledge_items (
  id TEXT PRIMARY KEY,
  source_file TEXT,
  file_type TEXT,
  indexed_at TIMESTAMP,
  metadata JSON
);

-- Контакты
CREATE TABLE contacts (
  id TEXT PRIMARY KEY,
  name TEXT,
  aliases JSON, -- ["Вася", "Владимир"]
  telegram_id TEXT,
  email TEXT
);
```

#### 4.2 Vector Database (ChromaDB/Pinecone)

**Структура**:
- Collection: `knowledge_base`
- Documents: Chunked text from PDFs/DOCX
- Embeddings: OpenAI `text-embedding-3-small`
- Metadata: `{source_file, chunk_index, date}`

**Использование**:
- Semantic search по документам
- RAG для контекстных ответов

---

### 5. Integration Layer

#### 5.1 Telegram Bot

**Назначение**: Отправка уведомлений и follow-up сообщений.

**Функции**:
- Отправка напоминаний о задачах
- Отправка draft follow-up после встреч
- Получение подтверждений от пользователя

**Интеграция**:
- Использовать существующий Telegram Bot API из legacy
- Создать сервис `telegram_service.py`

#### 5.2 Email (Опционально)

**Назначение**: Альтернатива Telegram для follow-up.

**Провайдер**: Resend или SendGrid

---

## Потоки данных

### Поток 1: Обработка задачи

```
User Input (Frontend)
  ↓
POST /api/tasks
  ↓
Next.js API Route
  ↓
Trigger TaskWorkflow (LangGraph)
  ↓
LLM: Extract Intent & Deadline
  ↓
Date Parser: Calculate Absolute Date
  ↓
Store in SQLite
  ↓
Schedule Notification (Task Queue)
  ↓
Return to Frontend
  ↓
Display Confirmation
```

### Поток 2: Обработка встречи

```
User Upload (Frontend)
  ↓
POST /api/meetings/process
  ↓
Next.js API Route (или FastAPI)
  ↓
Trigger MeetingWorkflow (LangGraph)
  ↓
[If Audio] Whisper API → Transcript
  ↓
LLM: Summarize
  ↓
LLM: Extract Participants (NER)
  ↓
Contacts Service: Match Participants
  ↓
LLM: Generate Draft Follow-up
  ↓
Store in SQLite
  ↓
Return to Frontend
  ↓
Display Summary + Draft
  ↓
User Clicks "Approve"
  ↓
POST /api/meetings/:id/send
  ↓
Telegram Service: Send Message
  ↓
Update Status in DB
```

### Поток 3: Индексация документа

```
User Upload (Frontend)
  ↓
POST /api/knowledge/index
  ↓
Next.js API Route
  ↓
Trigger KnowledgeWorkflow (LangGraph)
  ↓
Extract Text (PyPDF2, etc.)
  ↓
[If Images] GPT-4o-vision: Analyze
  ↓
Chunk Text (LangChain)
  ↓
Generate Embeddings (OpenAI)
  ↓
Index to Vector DB
  ↓
Store Metadata in SQLite
  ↓
Return to Frontend
  ↓
Display Success
```

---

## Безопасность

1. **API Keys**: Хранить в `.env`, не коммитить
2. **Authentication**: Добавить простую auth для production (NextAuth.js)
3. **Rate Limiting**: Ограничить количество запросов к LLM API
4. **Input Validation**: Валидация всех входных данных (Zod/Pydantic)
5. **File Upload**: Ограничить размер и типы файлов

---

## Масштабирование

### Текущая архитектура (MVP)
- SQLite для БД
- ChromaDB локально
- Next.js API Routes
- Serverless на Vercel

### Production-ready
- PostgreSQL (Supabase)
- Pinecone для Vector DB
- FastAPI для тяжелых workflows
- Redis для task queue
- CDN для статики

---

## Мониторинг и логирование

1. **Error Tracking**: Sentry
2. **Logging**: Structured logs (JSON)
3. **Metrics**: Vercel Analytics
4. **Health Checks**: `/api/health` endpoint

---

## Развертывание

### Development
- Локальный Next.js dev server
- SQLite + ChromaDB локально
- Mock внешних API (опционально)

### Production
- Vercel (Frontend + Next.js API)
- Railway/Render (FastAPI, если используется)
- Supabase (PostgreSQL)
- Pinecone (Vector DB)

---

**Last Updated**: 2025-01-20
**Version**: 1.0
