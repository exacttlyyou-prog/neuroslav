# Аудит и план доработки проекта Digital Twin

Дата: 2025-01-28

---

## 1. Анализ текущего состояния

### 1.1 Архитектура проекта

**Компоненты и связи:**

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js 14, apps/web)                                  │
│  • (tabs): dashboard, meetings, tasks, context, chat, daily-checkin
│  • API Routes: прокси к FastAPI (NEXT_PUBLIC_API_URL || localhost:8000)
└────────────────────────────┬────────────────────────────────────┘
                             │ fetch → Backend
┌────────────────────────────▼────────────────────────────────────┐
│  Backend (FastAPI, apps/api)                                     │
│  • Роутеры: /api/tasks, /api/meetings, /api/knowledge, /api/notion,
│    /api/chat, /api/daily-checkin, /api/telegram, /api/reports, cache, monitoring
│  • Workflows: meeting_workflow, task_workflow, knowledge_workflow
│  • Сервисы: ollama, notion, telegram, rag, context_loader, transcription, recording…
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
   SQLite (digital_twin.db)   ChromaDB (vector_db)   Ollama (localhost:11434)
        │                    │                    │
        └────────────────────┴────────────────────┘
                             │
   Внешние: Notion API, Telegram Bot API, Whisper (транскрипция)
```

**Дополнительно:**
- **api/index.py** (корень) — Vercel serverless adapter, подключает `apps/api.app.main`
- **apps/agent-worker** — TypeScript‑воркер с утилитами для Notion (отдельный процесс при `launch.sh`)
- **legacy** — `_legacy_archive_v1`, `_legacy_archive_v2` — старые вырезы, в текущем коде не участвуют

**Поток данных (встреча):**
- Пользователь → Next.js `/api/meetings` (POST) → FastAPI `/api/meetings/process` → `MeetingWorkflow` → SQLite, RAG, (опционально Telegram после approve)
- «Последняя встреча» из Notion: Next.js `/api/notion/last-meeting` → FastAPI `/api/notion/last-meeting` → NotionService / MCP / Playwright fallback

### 1.2 Что реализовано и работает

| Область | Статус | Комментарий |
|--------|--------|-------------|
| Запуск | ✅ | `launch.sh` поднимает backend, frontend, agent-worker, проверяет Ollama, BlackHole, .env |
| Обработка встречи | ✅ | POST transcript/audio → транскрипция (Whisper), анализ (Ollama), участники/проекты/action items, сохранение в БД и RAG |
| Список встреч | ✅ | GET /api/meetings, фильтр по status |
| Approve & Send | ✅ | MeetingResults вызывает POST /api/meetings/:id/approve → FastAPI approve-and-send → Telegram |
| Задачи | ✅ | TaskWorkflow: извлечение intent/deadline (Ollama), сохранение, опционально создание в Notion |
| Knowledge/RAG | ✅ | KnowledgeWorkflow: извлечение текста, чанки, ChromaDB, SQLite metadata |
| Notion: чтение | ✅ | Страницы, базы (People, Projects, Glossary), последний блок встречи, поиск, AI-Context pages |
| Notion: запись | ✅ | create_meeting_in_db, create_task_in_notion, save_meeting_summary, save_meeting_minutes, ensure_required_databases |
| Telegram | ✅ | Webhook, отправка саммари/draft, верификация токена при старте |
| Запись встречи | ✅ | RecordingService, /start, /stop, /status |
| Daily check-in | ✅ | SchedulerService, DailyCheckinService, роутер |
| Чат | ✅ | Роутер и агенты (task, meeting, knowledge, rag, default) |
| Vercel | ⚠️ | Только FastAPI через api/index.py; frontend и Next.js API routes отдельно не задеплоены в текущем vercel.json |

### 1.3 Незавершённые части (TODO и неиспользуемый код)

**Явные TODO в коде:**
- `apps/web/components/forms/MeetingUploadForm.tsx:146` — «TODO: реализовать отправку через API» — по факту отправка уже есть в `MeetingResults` через `/api/meetings/:id/approve`; в форме передаётся `onSend` и `result.meeting.draftMessage` (несуществующее поле).
- `apps/api/app/workflows/task_workflow.py:93` — «TODO: Реализовать планирование через task queue или cron» — уведомления по deadline не планируются.
- `_legacy_archive_v1`: TODO по Gemini, Google Calendar — архив, не трогать.

**Неиспользуемый / обрывочный код:**
- `MeetingUploadForm`: передаёт `onSend` в `MeetingResults`, в то время как у `MeetingResults` в интерфейсе объявлен только `onApproved`; колбэк после отправки не срабатывает.
- В колбэке «onSend» используется `result.meeting.draftMessage` — у `MeetingProcessingResponse` нет вложенного `meeting`, есть `draft_message` (приведёт к падению при вызове).
- Дублирование: в `main.py` есть отдельный `@app.get("/api/notion/parser/status")`, в `routers/notion.py` — `@router.get("/parser/status")`; оба под префиксом /api/notion дают двойной маршрут при подключении notion + notion_webhook.

### 1.4 Противоречия и дублирование

**Дублирование логики:**
- **Notion «последняя встреча»:** цепочка MCP → Next.js fetch-via-mcp → Notion API → Playwright реализована в `routers/notion.py` (last-meeting/auto). Next.js route `/api/notion/last-meeting` проксирует только в FastAPI; `/api/notion/fetch-via-mcp` используется бэкендом при обращении к Next.js как к прокси к MCP — связка запутанная, но согласована.
- **Parser status:** в main зарегистрирован `get_parser_status` по `/api/notion/parser/status`, плюс в notion-роутере свой `get_parser_status` по тому же пути — при двух роутерах с prefix `/api/notion` один из них перекрывает другой (порядок включения: notion, потом notion_webhook).
- **Конфиг .env:** в QUICK_START — `apps/api/.env`; в launch.sh — и корень, и `apps/api`; в config.py — `BASE_DIR.parents[3]` + `.env` в корне. Фактически config ищет корневой .env, launch копирует корневой в apps/api — возможна рассинхронизация.

**Конфликтующие подходы:**
- ARCHITECTURE.md описывает «Next.js API Routes для CRUD» и «FastAPI опционально для тяжёлых workflow». Фактически вся логика в FastAPI, Next.js только проксирует — документ не совпадает с реализацией.
- NOTION_INTEGRATION.md: «при обработке встречи автоматически создаётся страница в Notion». В `meeting_workflow.py` явно закомментировано/не вызывается создание страницы («Страница встреч Notion используется только для чтения»), в ответе только `notion_page_id` сохраняется для связи.
- README: «Автоматическое сохранение в Notion» — без доп. настроек после обработки встречи страница в Notion не создаётся.

---

## 2. Проблемы и блокеры

### 2.1 Технические (баги, интеграция)

- **meeting_workflow.py:** на строках 77 и 82 используется `await asyncio.sleep(2)`, а `import asyncio` выполняется только на строке 103 — при повторных попытках транскрипции будет `NameError`. Нужно вынести `import asyncio` в начало файла.
- **MeetingUploadForm:** обращение к `result.meeting.draftMessage` вызовет падение; прописка `onSend` вместо `onApproved` мешает колбэку «после отправки».
- **Ответ по встрече:** бэкенд в `process_meeting` не возвращает `transcript` в JSON; в Next.js route в ответ клиенту `transcript` тоже не прокидывается. На фронте в MeetingResults есть блок «Транскрипция» — без `result.transcript` он всегда «Транскрипция недоступна».
- **approve route (Next.js):** шлёт в бэкенд FormData (summary, participants как JSON-строки). FastAPI `approve-and-send` принимает Form — контракт совпадает, но при разработке легко ошибиться; единый JSON было бы проще сопровождать.
- **Порядок роутов meetings:** в FastAPI объявлены и `/process`, и `/{meeting_id}/approve-and-send`, и `/start`, `/stop`, `/status`. Маршруты без path-параметров объявлены после маршрутов с `{meeting_id}`, конфликтов нет, но при добавлении новых путей под `/api/meetings/…` порядок нужно учитывать.

### 2.2 Концептуальные

- **Роль Notion для встреч:** неочевидно, когда создаётся страница встречи, когда только читается. Сейчас по умолчанию только чтение (last-meeting) и сохранение `notion_page_id` в БД; явного сценария «всегда создавать страницу в Notion после разбора» нет.
- **Где живёт «последняя встреча»:** одновременно страница Notion (MCP/API/Playwright), SQLite (встречи после process), RAG — нужно явно описать, какой источник считается источником правды для какого сценария.
- **Уведомления по задачам:** по ARCHITECTURE планируются «Schedule Notification (Task Queue)», в коде — только TODO; нет ни очереди, ни cron для дедлайнов задач.

### 2.3 Зависимости

- **requirements.txt (корень / Vercel):** ChromaDB, Playwright, тяжёлые ML-зависимости осознанно отключены для Vercel; на Vercel не будет RAG, индексации документов и Playwright/MCP fallback для Notion. Локально всё ставится из `apps/api/requirements.txt`.
- **Конфиг:** для полного сценария нужны NOTION_TOKEN, NOTION_MEETING_PAGE_ID, TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID; для записи встреч — Ollama, BlackHole, при необходимости Whisper (в transcription_service). Неочевидная зависимость: часть сценариев «последней встречи» завязана на MCP/Next.js, что не отражено в типовой инструкции по .env.

---

## 3. Интеграция с Notion

### 3.1 Как реализовано

- **Клиент:** `NotionService` (notion_client, AsyncClient, версия 2025-09-03), инициализация только при наличии `NOTION_TOKEN`.
- **Чтение:**  
  - страницы и блоки: `get_page_content`, `get_last_meeting_block`, `get_last_meeting_content`, `_get_all_blocks_recursive`, `_extract_text_from_block`;  
  - базы: `get_contacts_from_db`, `get_projects_from_db`, `get_glossary_from_db`, `get_database_data_sources`, `_query_database`;  
  - поиск: `search_in_notion`;  
  - AI-Context: `get_ai_context_pages`.
- **Запись:**  
  - `create_meeting_in_db`, `save_meeting_summary`, `save_meeting_to_ai_context`, `append_to_meeting`;  
  - `create_task_in_notion`;  
  - `ensure_required_databases`, `_create_people_database`, `_create_projects_database`, `_create_meetings_database`, `_create_tasks_database`;  
  - отчёты и минуты: `save_daily_report`, `get_or_create_daily_reports_database`, `save_meeting_minutes`, `get_or_create_meeting_minutes_page`.
- **Обход ограничений API (meeting-notes и т.п.):**  
  - `NotionMCPService` — локальный MCP;  
  - Next.js `/api/notion/fetch-via-mcp` — обёртка/прокси;  
  - `NotionPlaywrightService` — браузерный fallback.  
  В `routers/notion.py` в last-meeting/auto порядок: MCP → Next.js route → Notion API → Playwright.

### 3.2 Что планировалось, но не делается в основном сценарии

- **NOTION_INTEGRATION.md:** «при обработке встречи автоматически создается страница в Notion» — в `meeting_workflow` создание/обновление страницы встречи не вызывается, только передаётся и сохраняется `notion_page_id`.
- «Если указан notion_page_id, контент добавляется на существующую страницу» — в коде добавления на переданную страницу нет.
- Рекомендуемые сценарии «хранилище истории», «календарь дедлайнов», «база знаний проектов», «глоссарий для контекста», «AI-Context как источник для RAG» — частично есть (глоссарий, AI-Context, RAG), но без явного product-описания и без автоматического создания страниц встреч.

---

## 4. Приоритезированный план действий

### Критичные (без этого ломается работа)

| # | Задача | Действие | Сложность | Зависимости |
|---|--------|----------|-----------|-------------|
| 1 | Исправить NameError в meeting_workflow | В начале `meeting_workflow.py` добавить `import asyncio` (и убрать дублирующий import внутри функции). | 0.5 ч | — |
| 2 | Устранить падение в MeetingUploadForm | Убрать использование `result.meeting.draftMessage`; передавать в `MeetingResults` колбэк как `onApproved` (или расширить интерфейс и вызывать после успешной отправки). | 0.5 ч | — |
| 3 | Прокинуть transcript в ответе встречи | В `meeting_workflow` включить `transcript` в возвращаемый dict; в Next.js POST /api/meetings при проксировании добавить `transcript: data.transcript` в объект ответа. | 0.5 ч | — |

### Важные (ключевой функционал)

| # | Задача | Действие | Сложность | Зависимости |
|---|--------|----------|-----------|-------------|
| 4 | Убрать дублирование parser/status | Оставить один обработчик `/api/notion/parser/status`: либо только в notion-роутере, либо только в main; второй удалить. | 0.5 ч | — |
| 5 | Заделить создание страницы встречи в Notion | Определить сценарий (всегда / по флагу / по наличию notion_page_id). В `MeetingWorkflow` после сохранения в SQLite вызывать, например, `notion.create_meeting_in_db(...)` или `save_meeting_to_ai_context` при выполнении условий. Подключить к конфигу (например NOTION_AUTO_CREATE_MEETING_PAGE). | 2–4 ч | Решение по продукту |
| 6 | Планирование уведомлений по задачам | Реализовать в task_workflow вызов SchedulerService (или отдельной очереди) при наличии deadline: поставить задачу «напомнить» на deadline. Поведение при сбоях и перезапуске — отдельно. | 4–8 ч | SchedulerService уже есть |
| 7 | Уточнить документацию по конфигу | В README/QUICK_START явно указать: корень vs apps/api для .env, какие переменные обязательны для встреч/Notion/Telegram/Ollama/MCP. | 1 ч | — |

### Улучшения (можно отложить)

| # | Задача | Действие | Сложность | Зависимости |
|---|--------|----------|-----------|-------------|
| 8 | Унифицировать approve-and-send на JSON | Перевести FastAPI `approve-and-send` на приём JSON body вместо Form; Next.js route слать JSON. | 1–2 ч | — |
| 9 | Привести ARCHITECTURE.md в соответствие с кодом | Описать фактическую схему: Next.js только прокси к FastAPI; все CRUD и workflows в FastAPI. Убрать формулировки «опциональный FastAPI». | 1 ч | — |
| 10 | Удалить/ослабить устаревший STATUS.md | В apps/web/STATUS.md убрать «API routes возвращают заглушки» и т.п.; кратко описать текущее состояние или ссылку на этот аудит. | 0.5 ч | — |
| 11 | Регламент по Notion | В NOTION_INTEGRATION.md или в отдельном разделе описать: когда создаётся страница встречи, когда только читается; источники «последней встречи» (Notion vs БД vs RAG). | 1 ч | Решение по п.5 |
| 12 | Деплой frontend на Vercel | Если нужен публичный веб-интерфейс: вынести/продублировать конфиг сборки под монорепо (apps/web как root для frontend-проекта на Vercel) или описать раздельный деплой API и frontend. | 2–4 ч | Требования к деплою |

---

## 5. Рекомендации

### Что удалить

- **Легаси:** не трогать `_legacy_archive_v1` и `_legacy_archive_v2` в рамках текущих фич; при желании пометить в README как «архив, не для продакшена».
- **Дублирующий парсер:** один из двух обработчиков `/api/notion/parser/status` (в main или в notion router) убрать.
- **Мёртвый код в MeetingUploadForm:** колбэк с `result.meeting.draftMessage` и неверное имя пропа `onSend` — либо исправить использование, либо упростить до одного `onApproved` и убрать лишние логи.

### Что упростить

- **Цепочка «последняя встреча»:** в коде уже есть чёткий порядок (MCP → Next.js → API → Playwright); в документации и логах явно зафиксировать этот порядок и условия выбора (например, «если MCP недоступен — Next.js, иначе API, иначе Playwright»).
- **Два .env:** выбрать один источник правды (корень или apps/api) и в launch.sh/README описать только его; при необходимости оставить один шаг копирования с явным упоминанием в инструкции.
- **Notion для встреч:** зафиксировать один режим по умолчанию (только чтение **или** чтение + запись при определённых условиях) и убрать противоречия между NOTION_INTEGRATION, README и кодом.

### Какую документацию добавить

- **Текущий аудит:** этот файл (AUDIT_AND_PLAN.md) — как срез состояния и план работ.
- **Конфиг:** одна страница (или раздел в QUICK_START) «Переменные окружения»: имя, обязательность, для чего нужна, пример.
- **Notion-сценарии:** когда создаём страницу встречи, когда только читаем, откуда берётся «последняя встреча» (включая MCP/Playwright).
- **Деплой:** если Vercel остаётся в планах — отдельный короткий гайд: что именно деплоится (только API или API+frontend), какие переменные и лимиты (ChromaDB/Playwright отключены и т.д.).

---

*Конец аудита.*
