# Деплой только API на Vercel (бот, webhook, /health)

Чтобы по URL проекта открывался **API** (FastAPI), а не фронт, и Vercel не подставлял Next.js, деплой API идёт из папки **deploy-api/** (в ней нет package.json и Next.js).

## 1. Настройки проекта API в Vercel

Создай новый проект или открой существующий **только для API**:

1. **Settings** → **General**
   - **Root Directory** — **deploy-api** (именно эта папка; тогда Vercel не видит корневой package.json и не переключает на Next.js).
   - **Framework Preset** — **Other**.

2. **Build Command** в настройках проекта **не применяется** при наличии `builds` в vercel.json — Vercel его игнорирует. Код API лежит в **deploy-api/app** (копия apps/api/app); при обновлении бэкенда нужно заново скопировать: `cp -R apps/api/app deploy-api/app` и закоммитить.

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

## 4. База данных на Vercel

На Vercel автоматически используется `sqlite:////tmp/digital_twin.db` (папка `/tmp` доступна для записи, но данные не сохраняются между холодными стартами). Для постоянного хранения нужен внешний Postgres и переменная `DATABASE_URL`.

## 5. Если всё ещё 404 или 500

- **500:** часто из‑за падения при старте (БД, импорты). Убедись, что **Build Command** = `bash copy-app.sh`. На Vercel БД по умолчанию в `/tmp` (см. п. 4). Смотри **Runtime Logs** деплоя — там будет traceback.
- **404:** в **Build Logs** проверить: есть ли сборка Python (`api/index.py`), нет ли ошибок. **Build Command** должен быть `bash copy-app.sh`.
