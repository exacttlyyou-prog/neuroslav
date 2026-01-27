# Инструкция по деплою на Vercel и настройке Telegram Webhook

## Шаг 1: Подготовка к деплою

### 1.1. Установка Vercel CLI (если еще не установлен)

```bash
npm i -g vercel
```

### 1.2. Логин в Vercel

```bash
vercel login
```

## Шаг 2: Настройка переменных окружения

### 2.1. Создай файл `.env` в корне проекта (если еще нет)

Добавь необходимые переменные:

```env
# Telegram
TELEGRAM_BOT_TOKEN=твой_токен_от_BotFather
ADMIN_CHAT_ID=твой_chat_id
TELEGRAM_WEBHOOK_URL=https://твой-проект.vercel.app

# Notion (если используется)
NOTION_TOKEN=твой_notion_token
NOTION_MCP_TOKEN=твой_mcp_token
NOTION_MEETING_PAGE_ID=твой_page_id
NOTION_PEOPLE_DB_ID=твой_db_id
NOTION_PROJECTS_DB_ID=твой_db_id
NOTION_GLOSSARY_DB_ID=твой_db_id

# Ollama (если используется локально, для Vercel не нужно)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b

# Database (для Vercel используй внешнюю БД, например PostgreSQL)
DATABASE_URL=postgresql://user:password@host:port/dbname
```

### 2.2. Добавь переменные в Vercel Dashboard

После первого деплоя:

1. Зайди в [Vercel Dashboard](https://vercel.com/dashboard)
2. Выбери свой проект
3. Перейди в **Settings** → **Environment Variables**
4. Добавь все переменные из `.env` файла

**Важно:** Для `TELEGRAM_WEBHOOK_URL` сначала задеплой проект, получи URL, затем добавь переменную и сделай redeploy.

## Шаг 3: Деплой на Vercel

### 3.1. Вариант A: Деплой через Vercel Dashboard (рекомендуется)

1. Зайди на [vercel.com](https://vercel.com) и войди в аккаунт
2. Нажми **Add New...** → **Project**
3. Подключи GitHub репозиторий (если еще не подключен):
   - Нажми **Import Git Repository**
   - Выбери репозиторий `exacttlyyou-prog/neuroslav` (или свой)
   - Нажми **Import**
4. Настрой проект:
   - **Project Name:** `neuroslav-api` (или другое название)
   - **Framework Preset:** Other (или оставь как есть)
   - **Root Directory:** `./` (корень проекта)
   - **Build Command:** оставь пустым (Vercel сам определит)
   - **Output Directory:** оставь пустым
   - **Install Command:** оставь пустым
5. Нажми **Deploy**

### 3.2. Вариант B: Деплой через терминал

```bash
cd "/Users/slava/Desktop/коллеги, обсудили"
vercel --prod
```

Vercel спросит:
- **Set up and deploy?** → `Y`
- **Which scope?** → выбери свой аккаунт
- **Link to existing project?** → `N` (для первого раза)
- **What's your project's name?** → введи название (например: `neuroslav-api`)
- **In which directory is your code located?** → `./` (корень проекта)

### 3.3. После деплоя получи URL

Vercel покажет URL вида: `https://твой-проект.vercel.app`

**Скопируй этот URL!** Он понадобится для настройки webhook.

## Шаг 4: Настройка Telegram Webhook

### 4.1. Обнови переменную окружения в Vercel

1. Зайди в Vercel Dashboard → Settings → Environment Variables
2. Добавь или обнови `TELEGRAM_WEBHOOK_URL`:
   ```
   TELEGRAM_WEBHOOK_URL=https://твой-проект.vercel.app
   ```
3. Сохрани изменения

### 4.2. Вариант A: Автоматическая настройка (рекомендуется)

Webhook настроится автоматически при следующем деплое, если:
- `TELEGRAM_BOT_TOKEN` установлен
- `TELEGRAM_WEBHOOK_URL` установлен

Просто сделай redeploy:

```bash
vercel --prod
```

Или через Vercel Dashboard: **Deployments** → выбери последний деплой → **Redeploy**

### 4.3. Вариант B: Ручная настройка через скрипт

Если автоматическая настройка не сработала:

```bash
cd apps/api
source .venv/bin/activate  # или активируй виртуальное окружение
python scripts/setup_telegram_webhook.py https://твой-проект.vercel.app/api/telegram/webhook
```

## Шаг 5: Проверка работы

### 5.1. Проверь, что webhook настроен

Отправь сообщение боту в Telegram. Если бот отвечает — всё работает!

### 5.2. Проверь логи в Vercel

1. Зайди в Vercel Dashboard → **Deployments**
2. Выбери последний деплой → **Functions** → выбери функцию
3. Смотри логи в реальном времени

### 5.3. Проверь статус webhook через API

```bash
curl https://api.telegram.org/bot<ТВОЙ_ТОКЕН>/getWebhookInfo
```

Должен вернуть JSON с информацией о webhook.

## Шаг 6: Обновление кода (последующие деплои)

После изменений в коде:

```bash
git add -A
git commit -m "Описание изменений"
git push
```

Vercel автоматически задеплоит изменения, если настроен GitHub integration.

Или вручную:

```bash
vercel --prod
```

## Решение проблем

### Проблема: Webhook не работает

1. Проверь, что `TELEGRAM_WEBHOOK_URL` правильный (без `/api/telegram/webhook` в конце)
2. Проверь, что `TELEGRAM_BOT_TOKEN` валидный
3. Проверь логи в Vercel Dashboard
4. Попробуй настроить webhook вручную через скрипт

### Проблема: Бот не отвечает

1. Проверь логи в Vercel Dashboard
2. Проверь, что webhook настроен: `curl https://api.telegram.org/bot<ТОКЕН>/getWebhookInfo`
3. Проверь, что endpoint доступен: `curl https://твой-проект.vercel.app/api/telegram/webhook` (должен вернуть 405 или другую ошибку, но не 404)

### Проблема: Ошибки при деплое

1. Проверь, что все зависимости в `apps/api/requirements.txt`
2. Проверь, что `vercel.json` настроен правильно
3. Смотри логи деплоя в Vercel Dashboard

## Полезные команды

```bash
# Просмотр текущих деплоев
vercel ls

# Просмотр логов
vercel logs

# Удаление проекта
vercel remove

# Локальный запуск (для тестирования)
vercel dev
```

## Структура проекта для Vercel

Vercel использует `vercel.json` для конфигурации:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "api/index.py"
    }
  ],
  "env": {
    "PYTHON_VERSION": "3.11"
  }
}
```

Файл `api/index.py` — это адаптер для Vercel, который подключает FastAPI приложение.
