# Быстрый деплой на Vercel

## Команды для деплоя

```bash
# 1. Установка Vercel CLI (если еще не установлен)
npm i -g vercel

# 2. Логин
vercel login

# 3. Деплой
cd "/Users/slava/Desktop/коллеги, обсудили"
vercel --prod
```

## После деплоя

1. **Скопируй URL** из вывода команды (например: `https://твой-проект.vercel.app`)

2. **Добавь переменные окружения в Vercel Dashboard:**
   - Зайди: https://vercel.com/dashboard → выбери проект → Settings → Environment Variables
   - Добавь:
     ```
     TELEGRAM_BOT_TOKEN=твой_токен
     ADMIN_CHAT_ID=твой_chat_id
     TELEGRAM_WEBHOOK_URL=https://твой-проект.vercel.app
     ```
   - И другие переменные из `.env`

3. **Redeploy** (чтобы применить переменные):
   ```bash
   vercel --prod
   ```
   
   Или через Dashboard: Deployments → Redeploy

4. **Проверь работу:** отправь сообщение боту в Telegram

## Если webhook не настроился автоматически

```bash
cd apps/api
source .venv/bin/activate
python scripts/setup_telegram_webhook.py https://твой-проект.vercel.app/api/telegram/webhook
```

## Обновление кода

```bash
git add -A
git commit -m "Описание"
git push
# Vercel задеплоит автоматически (если настроен GitHub integration)
```

Подробная инструкция: см. `DEPLOY_VERCEL.md`
