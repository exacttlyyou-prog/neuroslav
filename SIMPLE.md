# Простая системка

Один сценарий: **написал боту в Telegram → получил ответ**. Данные (контекст, задачи, встречи) — в Notion; бэкенд с ними работает.

---

## Продакшен (Vercel): ничего локально не запускаешь

**Цель деплоя — чтобы бот работал без ручного запуска сервера.** Telegram шлёт запросы на твой URL на Vercel, бэкенд там обрабатывает и отвечает.

1. **Задеплой бэкенд на Vercel** (проект из **корня** репо, с `vercel.json` и `api/index.py` — это API, не Next.js).  
2. **В Vercel Dashboard → проект API → Settings → Environment Variables** задай те же ключи, что в `.env`:
   - **Telegram:** `TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`, `TELEGRAM_WEBHOOK_URL` (URL этого же проекта API, без пути).
   - **Notion** (данные проекта хранятся там — без них бот не видит контекст/задачи/встречи): `NOTION_TOKEN`, `NOTION_MEETING_PAGE_ID`, `NOTION_PEOPLE_DB_ID`, `NOTION_PROJECTS_DB_ID`; при использовании — `NOTION_MCP_TOKEN`, `NOTION_AI_CONTEXT_PAGE_ID`, `NOTION_TASKS_PAGE_ID`, `NOTION_GLOSSARY_DB_ID`, `NOTION_WEBHOOK_SECRET`.
   После деплоя бэкенд при старте сам пропишет webhook в Telegram (если заданы токен и TELEGRAM_WEBHOOK_URL).
3. **Один раз настроить webhook** (с `https://` в начале):
   ```bash
   cd "/Users/slava/Desktop/коллеги, обсудили/apps/api"
   source .venv/bin/activate
   python scripts/setup_telegram_webhook.py https://твой-проект-api.vercel.app/api/telegram/webhook
   ```
   Важно: URL должен быть **проекта API** (тот, где деплоится `api/index.py`), а не фронта (Next.js). Если у тебя один проект из корня — используй его URL.

4. **Готово.** Локально ничего запускать не нужно. Пишешь боту — ответ идёт с Vercel. Логи смотри в Vercel Dashboard → Deployments → последний деплой → Logs.

**Если бот молчит или по URL API открывается фронт / 404 на /health:**
- Webhook должен указывать на **проект API** (не на фронт). URL вида `neuroslav-web00-xxx.vercel.app` — это **фронт** (Next.js), там нет `/api/telegram/webhook` → 404, бот не ответит. Нужен отдельный проект в Vercel из **корня** репо (`vercel.json` + `api/index.py`), и webhook = `https://<этот-проект>.vercel.app/api/telegram/webhook`.
- Если по URL проекта API открывается фронт или 404 на `/health` — в проекте API нужно **отключить Node-сборку**: Build Command = `echo "api-only"`, Output Directory пусто. Пошагово: **[DEPLOY_API_VERCEL.md](DEPLOY_API_VERCEL.md)**.
- В Vercel проверь, что заданы переменные и что URL webhook с **https://**.

---

## Где настройки в Vercel

**Важно:** страница **Deployment Details** (где Build Logs, Deployment Settings, Runtime Logs) — это настройки *одного деплоя*. Переменные окружения задаются в **настройках проекта**, не на этой странице.

**Переменные окружения (TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID и т.д.):**

1. Зайди на [vercel.com](https://vercel.com) → в левом сайдбаре выбери **проект** (например neuroslav-web00), а не «Deployments».
2. В верхней панели **этого проекта** нажми **Settings** (не «Deployment Settings» из карточки деплоя).
3. В левом сайдбаре настроек проекта выбери **Environment Variables**.
4. Добавь переменные (Name / Value), выбери окружение Production (и при желании Preview), нажми Save.

**Логи (Runtime Logs):**  
В том же проекте: **Deployments** → открой последний деплой → внизу блок **Runtime Logs** (или **Functions** → выбери функцию → логи). Там видно запросы и ошибки при работе бота.

**Два проекта в Vercel:**

| Проект | Что деплоится | URL пример | Webhook? |
|--------|----------------|------------|----------|
| **neuroslav-web00** | Фронт (Next.js, `apps/web`) | `neuroslav-web00-xxx.vercel.app` | ❌ Нет — там нет `/api/telegram/webhook`, будет 404. |
| **API** (название любое) | Бэкенд из **корня** репо (`vercel.json`, `api/index.py`) | `https://neuroslav-api-xxx.vercel.app` | ✅ Да — webhook и переменные (Telegram, Notion) задавать здесь. |

Если проекта API нет: Add New → Project → тот же репо → **Root Directory** = `./` (корень), Framework = **Other** → Deploy. После деплоя скопируй URL этого проекта и настрой webhook на `https://<этот-url>/api/telegram/webhook`.

---

## Локально (для разработки)

### Что нужно один раз

1. **Python 3.11+** и **Ollama**.  
2. **Файл `.env`** с `TELEGRAM_BOT_TOKEN` и при желании `ADMIN_CHAT_ID`.  
3. **Webhook** — локально без туннеля Telegram до тебя не достучится; либо ngrok (см. QUICK_WEBHOOK.md), либо используй продакшен на Vercel.

### Запуск «только бот» локально

```bash
./launch_bot_only.sh
```

Один процесс — бэкенд на порту 8000. Логи: консоль и `/tmp/digital_twin_backend.log`. Остановка: **Ctrl+C**.  
Если webhook указывает на **Vercel**, то при сообщении боту запросы идут на Vercel, а не на localhost — локальные логи будут пустыми; смотри логи в Vercel.

---

## Что есть ещё (можно не трогать)

| Часть | Нужна для «просто бот»? |
|-------|--------------------------|
| **Frontend (Next.js)** | Нет. Удобства в браузере, но для ответов в Telegram не нужен. |
| **Agent-worker** | Нет. Обработка встреч/очередей — отдельный сценарий. |
| **launch.sh** | Запускает всё (бэкенд + фронт + agent-worker + проверки). Если хочешь «просто бот» — используй `launch_bot_only.sh`. |
| **Запись встреч, BlackHole** | Отдельный сценарий. Для «написал — ответил» не нужны. |

---

## Бот молчит

Кратко: **BOT_NO_RESPONSE.md** и **OPERATIONS.md**.  
Главное: есть ли в логах `WEBHOOK recv` после твоего сообщения? Нет — чини webhook/туннель/деплой.
