# План отладки и доработки — цифровой двойник (одна попытка)

**Цель:** проект должен задеплоиться на Vercel и дать минимально работающий контур: Telegram webhook отвечает, health — ок. Остальной функционал (встречи, Notion, RAG, напоминания) — в режиме «graceful degradation»: не падать, при отсутствии сервисов отвечать понятно.

---

## 1. Диагностика: почему не деплоится и не работает

### 1.1 Деплой

| Что проверить | Где смотреть | Типичная причина |
|---------------|--------------|-------------------|
| Ошибка билда | Vercel Dashboard → Deployments → Build logs | Конфликт зависимостей, неверный Python; тяжёлые пакеты (langchain, chromadb, playwright) |
| Какой requirements используется | Корень репо: `requirements.txt` | **Vercel всегда берёт requirements.txt из корня.** Файл `apps/api/requirements.txt` при деплое не используется. |
| Python | `runtime.txt` / `.python-version` | Vercel по доке использует **Python 3.12** и не даёт менять. Если в pyproject.toml жёстко `<3.12` — возможны конфликты. |

**Текущее состояние:** в корне `requirements.txt` уже «лёгкий». Ошибка билда: `uv add -r requirements.txt` → «No solution found when resolving dependencies for split (markers: python_full_version >= '3.14')» — uv тянет транзитивы (в т.ч. langchain-core), у части из них маркер Python 3.14+.

**Сделано:** (1) корневой `pyproject.toml` переименован в `pyproject.toml.bak`, чтобы Vercel не запускал uv в режиме «проект + requirements» и не смешивал ограничения; (2) в `requirements.txt` зафиксированы версии `python-telegram-bot==21.7`, `pydantic==2.9.2`, `pydantic-settings==2.6.1`, чтобы не подтягивались минорные версии с маркерами 3.14.

### 1.2 Старт приложения (runtime)

| Что ломается | Где | Решение |
|--------------|-----|---------|
| Запись в жёстко заданный путь | `main.py` → `open("/Users/slava/.../.cursor/debug.log")` | На Vercel такого каталога нет → **исключение при startup**. Убрать или писать только если путь существует и доступен. |
| Неверный импорт | `telegram_webhook.py` → `from apps.api.app.db.database import AsyncSessionLocal` | При PYTHONPATH = `apps/api` модуль — `app.db.database`. **Исправить на** `from app.db.database import AsyncSessionLocal`. |
| Тяжёлый startup | main при старте: Notion, Telegram webhook, BackgroundParser, ProactiveService, SchedulerService | На serverless инстанс живёт запрос; фоновые циклы бессмысленны. Любой из сервисов может тянуть ollama/chromadb при импорте и падать. | Делать запуск фоновых сервисов и «тяжёлых» проверок только когда **не** Vercel (например по `VERCEL=1` или отдельной переменной `DEPLOY_ENV=vercel`). |

### 1.3 Функционал после старта

| Сценарий | Зависимости | На Vercel |
|----------|-------------|-----------|
| `GET /`, `GET /health` | Только FastAPI | Должно работать |
| `POST /api/telegram/webhook` | telegram, db, возможно agent_router | Роут сработает; при вызове агентов понадобятся ollama/rag. Без них — либо ошибка, либо заглушка. |
| Ollama (классификация, генерация) | ollama, локальная сеть | **Нет** — на Vercel нет доступа к localhost. Нужен fallback: «без LLM пока недоступен» или внешний API. |
| RAG /knowledge | chromadb, sentence-transformers | В корневом requirements их нет → RAGService при поиске выдаст «Embedding model не доступен». Нужен явный fallback в коде. |
| Notion | notion-client, токен | Работает, если токен в env и сеть есть. |
| Запись встреч, транскрипция | recording, внешний сервис транскрипции | Запись/транскрипция обычно не на serverless; на Vercel оставляем заглушку или отключение. |

---

## 2. План доработки (приоритеты)

### Фаза A — «чтобы задеплоилось и не падало при старте»

1. **Убрать падение при startup**
   - Удалить или обернуть в «если путь существует» запись в `/Users/slava/.../debug.log` в `main.py`.
   - В `telegram_webhook.py` заменить `from apps.api.app.db.database` на `from app.db.database`.

2. **Один явный requirements для Vercel**
   - Оставить в **корне** один `requirements.txt`, по которому реально деплоим: только то, что нужно для webhook + health + БД + notion-client + telegram. Без ollama, chromadb, playwright, sentence-transformers.
   - При необходимости зафиксировать версии (как в текущем корневом requirements), чтобы не было «No solution found».

3. **Режим Vercel в коде**
   - В `main.py` при старте проверять окружение (например `os.getenv("VERCEL") == "1"` или своя переменная `DEPLOY_ENV=vercel`).
   - В этом режиме **не** запускать:
     - NotionBackgroundParser,
     - ProactiveService,
     - SchedulerService,
     - предзагрузку контекста (ContextLoader.preload_context),
     - мониторинг производительности (get_performance_monitor).
   - Оставить: init_db, проверку Telegram (и при наличии URL — set_webhook), по желанию — лёгкую проверку Notion (validate_token), всё в try/except без падения.

4. **Поведение при отсутствии тяжёлых сервисов**
   - `RAGService`: при `CHROMADB_AVAILABLE is False` или `embedding_model is None` метод `search_knowledge` не должен бросать исключение; возвращать пустой список и при желании логировать «RAG недоступен».
   - Вызовы Ollama (AgentRouter, агенты): при недоступности Ollama — не падать, возвращать короткое сообщение пользователю («Сейчас без AI» / «Доступно только в локальном режиме»).
   - Оформить это через уже существующие проверки/заглушки там, где вызываются Ollama/RAG, чтобы один сбой не ронял весь webhook.

### Фаза B — «минимально работающий цифровой двойник на проде»

5. **Что должно точно работать на Vercel**
   - Health: `GET /`, `GET /health` → 200.
   - Telegram webhook: команды `/start`, `/help`, `/tasks`, `/reminders`, `/meetings` (чтение из БД), список из кэша/БД без LLM.
   - Ответ на произвольное сообщение: либо заглушка «Сейчас без AI, доступны команды /tasks, /meetings…», либо ограниченная логика без ollama (например, жёсткие правила вместо классификатора).

6. **Что остаётся «только локально» или «позже»**
   - Запись/транскрипция встреч (требует процесс + диск/внешний сервис).
   - RAG с эмбеддингами (нужен либо внешний embedding API, либо вынос в отдельный сервис).
   - Генерация саммари, задачи из текста через LLM — при появлении внешнего API LLM можно включить и на Vercel.

7. **Notion на Vercel**
   - Оставить только то, что не требует тяжёлых зависимостей: чтение/запись через notion-client по токену из env. Без playwright, без локального парсера — только API.

8. **Напоминания / отложенные сообщения**
   - На serverless нет длительно живущего процесса. Планировщик «на 18:30» и отложенные сообщения возможны только через внешний кронтик (cron Vercel, отдельный воркер, облачный scheduler), который дергает HTTP endpoint. В рамках «одной попытки» достаточно зафиксировать это в плане и не ронять приложение при отсутствии SchedulerService в режиме Vercel.

---

## 3. Чеклист перед следующим деплоем

- [ ] В `main.py` нет записи в абсолютный путь к `.cursor/debug.log` (или она под существование каталога).
- [ ] В `telegram_webhook.py` импорт БД: `from app.db.database import AsyncSessionLocal` (не `apps.api.app.db`).
- [ ] В корне `requirements.txt` — только пакеты, допустимые на Vercel (без chromadb, playwright, sentence-transformers, ollama). Версии зафиксированы.
- [ ] В `main.py` при `VERCEL=1` (или аналоге) не стартуют BackgroundParser, ProactiveService, SchedulerService, тяжёлый ContextLoader/monitoring.
- [ ] RAG и вызовы Ollama при недоступности не роняют обработчик webhook; пользователь получает сообщение или пустой список вместо 500.
- [ ] В Vercel Dashboard в Environment Variables заданы минимум: `TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`, `TELEGRAM_WEBHOOK_URL` (после первого деплоя — URL вида `https://<project>.vercel.app`).
- [ ] После деплоя: `GET https://<project>.vercel.app/health` → 200; отправка боту в Telegram → ответ (хотя бы на `/start`).

---

## 4. Порядок работ (одна итерация)

1. Внести правки по п. 2 (фаза A): main.py (debug.log + режим Vercel), telegram_webhook.py (импорт), при необходимости — RAGService/Ollama fallback.
2. Убедиться, что корневой `requirements.txt` соответствует п. 3 чеклиста.
3. Закоммитить, запушить, дождаться деплоя на Vercel.
4. Пройти чеклист п. 3 по шагам.
5. Если билд или старт снова падает — по логам в Vercel (Build + Function logs) уточнить причину и повторить только точечные правки (зависимости или условный запуск сервисов).

---

## 5. Кратко по функционалу «цифровой двойник»

- **Запись встреч, транскрипция** — локально или отдельный воркер; на Vercel только приём и отображение уже готовых данных (если будут складываться через API).
- **Отправить коллеге / напомнить в заданное время** — через задачи в БД + внешний cron/scheduler, дергающий API; в коде — корректная работа без падений при выключенном SchedulerService на Vercel.
- **Хранение в Notion и обучение базы для управления** — через notion-client и, при наличии, отдельный RAG/embedding-сервис; на Vercel в первой итерации — только Notion API и заглушки RAG без падений.

Итог: фокус «одной попытки» — стабильный деплой, работающие health и Telegram webhook, никаких падений из-за отсутствующих сервисов; остальное — по мере готовности инфраструктуры (внешний LLM, RAG, кроны).
