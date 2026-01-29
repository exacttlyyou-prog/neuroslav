# Деплой только API на Vercel (бот, webhook, /health)

Чтобы по URL проекта открывался **API** (FastAPI), а не фронт, и Vercel не подставлял Next.js, деплой API идёт из папки **deploy-api/** (в ней нет package.json и Next.js).

## 1. Настройки проекта API в Vercel

Создай новый проект или открой существующий **только для API**:

1. **Settings** → **General**
   - **Root Directory** — **deploy-api** (именно эта папка; тогда Vercel не видит корневой package.json и не переключает на Next.js).
   - **Framework Preset** — **Other**.

2. **Settings** → **Build & Development** (или **Build and Output Settings**)
   - **Build Command** — задать: **`bash copy-app.sh`** (скрипт копирует `apps/api/app` в `deploy-api/app`, иначе функция падает с 500 — в бандле нет кода API).
   - **Output Directory** — оставить пустым.
   - **Install Command** — не менять.

После этого сборка идёт только по корневому `vercel.json`: собирается `api/index.py`, все запросы уходят в FastAPI.

## 2. Переменные окружения

В этом же проекте: **Settings** → **Environment Variables**. Задать:

- `TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`, `TELEGRAM_WEBHOOK_URL` (URL этого проекта без пути, например `https://neuroslav-web01.vercel.app`).
- Переменные Notion по необходимости (см. SIMPLE.md).

## 3. Деплой и проверка

1. Сохранить настройки → **Redeploy** (Deployments → последний деплой → Redeploy).
2. После деплоя открыть в браузере:
   - `https://<твой-api-проект>.vercel.app/health` — ожидается JSON `{"status":"healthy"}`, не 404.
   - `https://<твой-api-проект>.vercel.app/ready` — 200 и JSON с `status`, `checks`.
3. Один раз настроить webhook (если ещё не настроен):
   ```bash
   cd "/Users/slava/Desktop/коллеги, обсудили/apps/api"
   source .venv/bin/activate
   python scripts/setup_telegram_webhook.py https://<твой-api-проект>.vercel.app/api/telegram/webhook
   ```
4. Написать боту в Telegram. Логи — в Vercel: Deployments → последний деплой → **Runtime Logs**.

## 4. Если всё ещё 404

- В **Build Logs** деплоя проверить: есть ли сборка Python (`api/index.py`, `@vercel/python`), нет ли ошибок.
- Убедиться, что **Build Command** действительно переопределён (`echo "api-only"` или пусто), а не дефолтный `npm run build`.
