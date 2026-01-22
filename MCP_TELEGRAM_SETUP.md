# Настройка MCP серверов для Telegram

## Обзор

Интегрированы три популярных MCP сервера для работы с Telegram:

1. **telegram-bot-api** (`@xingyuchen/telegram-mcp`) - Node.js, Bot API
   - Отправка сообщений через бота
   - Поддержка rich text (HTML/Markdown)
   - Отправка фото, документов, видео
   - Управление чатами

2. **telegram-mtproto-read** (`sparfenyuk/mcp-telegram`) - Python, MTProto, read-only
   - Чтение сообщений из личного аккаунта
   - Просмотр диалогов
   - Загрузка медиа
   - Управление контактами

3. **telegram-mtproto-active** (`dryeab/mcp-telegram`) - Python, MTProto, активное управление
   - Отправка, редактирование, удаление сообщений
   - Поиск по чатам
   - Управление черновиками
   - Реакции на сообщения

## Установка

### 1. Telegram Bot API (telegram-bot-api)

**Требования:**
- Node.js и npm
- Telegram Bot Token от @BotFather

**Установка:**
```bash
# Установка происходит автоматически через npx при первом использовании
# Или вручную:
npm install -g @xingyuchen/telegram-mcp
```

**Настройка:**
1. Создайте бота через [@BotFather](https://t.me/BotFather) в Telegram
2. Получите Bot Token
3. Добавьте в `.env`:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   ```

### 2. Telegram MTProto Read-only (telegram-mtproto-read)

**Требования:**
- Python 3.10+
- `uv` package manager
- Telegram API credentials (API_ID, API_HASH)

**Установка:**
```bash
# Установка через uv
uv tool install git+https://github.com/sparfenyuk/mcp-telegram
```

**Настройка:**
1. Получите API credentials на [my.telegram.org/apps](https://my.telegram.org/apps)
2. Выполните первичную авторизацию:
   ```bash
   mcp-telegram sign-in \
     --api-id YOUR_API_ID \
     --api-hash YOUR_API_HASH \
     --phone-number +1234567890
   ```
3. Введите код подтверждения из Telegram
4. Если включена 2FA, введите пароль
5. Добавьте в `.env`:
   ```
   TELEGRAM_API_ID=your_api_id
   TELEGRAM_API_HASH=your_api_hash
   ```

### 3. Telegram MTProto Active (telegram-mtproto-active)

**Требования:**
- Python 3.10+
- `uv` package manager
- Telegram API credentials (API_ID, API_HASH)

**Установка:**
```bash
# Установка через uv
uv tool install mcp-telegram
```

**Настройка:**
1. Используйте те же API credentials, что и для read-only сервера
2. Выполните авторизацию:
   ```bash
   mcp-telegram login
   ```
3. Введите API_ID, API_HASH, номер телефона
4. Введите код подтверждения и 2FA пароль (если есть)
5. Переменные окружения уже настроены в `.env` (используются те же, что и для read-only)

## Конфигурация

Файл `.cursor/mcp.json` уже настроен и использует переменные из `.env`:

```json
{
  "mcpServers": {
    "telegram-bot-api": {
      "command": "npx",
      "args": ["-y", "@xingyuchen/telegram-mcp"],
      "env": {
        "TELEGRAM_BOT_TOKEN": "${TELEGRAM_BOT_TOKEN}"
      }
    },
    "telegram-mtproto-read": {
      "command": "uv",
      "args": ["tool", "run", "mcp-telegram"],
      "env": {
        "TELEGRAM_API_ID": "${TELEGRAM_API_ID}",
        "TELEGRAM_API_HASH": "${TELEGRAM_API_HASH}"
      }
    },
    "telegram-mtproto-active": {
      "command": "uv",
      "args": ["tool", "run", "mcp-telegram", "start"],
      "env": {
        "API_ID": "${TELEGRAM_API_ID}",
        "API_HASH": "${TELEGRAM_API_HASH}"
      }
    }
  }
}
```

## Переменные окружения

Добавьте в `.env`:

```bash
# Telegram Bot API (для telegram-bot-api)
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather

# Telegram MTProto (для telegram-mtproto-read и telegram-mtproto-active)
TELEGRAM_API_ID=your_api_id_from_my_telegram_org
TELEGRAM_API_HASH=your_api_hash_from_my_telegram_org
```

## Использование

После установки и настройки, MCP серверы будут доступны в Cursor через MCP протокол. AI ассистент сможет:

- **Через Bot API:**
  - Отправлять сообщения от имени бота
  - Отправлять медиа файлы
  - Управлять чатами

- **Через MTProto (read-only):**
  - Читать сообщения из вашего аккаунта
  - Просматривать диалоги
  - Загружать медиа
  - Управлять контактами

- **Через MTProto (active):**
  - Отправлять сообщения от вашего имени
  - Редактировать и удалять сообщения
  - Искать по чатам
  - Управлять черновиками

## Проверка работы

1. Перезапустите Cursor
2. MCP серверы должны автоматически подключиться
3. Проверьте в логах Cursor наличие подключений к MCP серверам

## Устранение неполадок

### Bot API не работает
- Проверьте, что `TELEGRAM_BOT_TOKEN` правильный
- Убедитесь, что бот запущен через @BotFather

### MTProto не работает
- Проверьте, что `uv` установлен: `uv --version`
- Проверьте, что выполнена авторизация: `mcp-telegram logout` и затем `mcp-telegram login`
- Убедитесь, что API_ID и API_HASH правильные

### Команда не найдена
- Для Python серверов: используйте полный путь к `uv` или добавьте в PATH
- Для Node.js: убедитесь, что `npx` доступен

## Дополнительные ресурсы

- [sparfenyuk/mcp-telegram](https://github.com/sparfenyuk/mcp-telegram)
- [dryeab/mcp-telegram](https://github.com/dryeab/mcp-telegram)
- [guangxiangdebizi/telegram-mcp](https://github.com/guangxiangdebizi/telegram-mcp)
- [Telegram Bot API Documentation](https://core.telegram.org/bots/api)
- [Telegram MTProto Documentation](https://core.telegram.org/api)
