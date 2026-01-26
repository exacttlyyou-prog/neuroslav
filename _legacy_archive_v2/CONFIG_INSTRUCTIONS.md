# Инструкция по настройке .env

Создайте файл `.env` в папке `apps/api/` и добавьте туда следующие переменные:

```env
# Настройки Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

# Notion API
# Получить токен: https://www.notion.so/my-integrations
NOTION_TOKEN=ntn_...

# ID страницы Notion (AI Context)
# Это 32 символа в конце URL страницы
NOTION_MEETING_PAGE_ID=...

# Telegram Уведомления
# Токен от @BotFather
TELEGRAM_BOT_TOKEN=...
# Ваш ID от @userinfobot
ADMIN_CHAT_ID=...
```

После сохранения файла перезапустите `./launch.sh`.
