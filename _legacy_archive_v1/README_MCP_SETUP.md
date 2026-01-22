# Настройка MCP Notion для получения AI Meeting Notes

## Текущая ситуация

У вас настроен **remote MCP сервер Notion** в Cursor с **14 инструментами**, включая `notion-fetch`, который может получать transcription блоки (AI meeting notes).

## Проблема

Transcription блоки (AI meeting notes) **недоступны** через стандартный Notion API. Для их получения требуется:
- Remote MCP сервер Notion с инструментом `notion-fetch`
- OAuth авторизация

## Решение

### Вариант 1: Использование через Cursor (рекомендуется)

1. **Получите данные через Cursor MCP:**
   - Откройте Command Palette (Cmd+Shift+P)
   - Найдите "MCP: Fetch Notion Page" или используйте MCP инструмент напрямую
   - Введите ID страницы: `2edfa7fd637180b98715fa9f348f90f9` или `ce32758331a5406694f86b8bd292605a`
   - Скопируйте JSON результат

2. **Сохраните результат в файл:**
   ```bash
   # Сохраните JSON в файл mcp_response.json в корне проекта
   ```

3. **Запустите скрипт:**
   ```bash
   python run_last_meeting.py
   ```

### Вариант 2: Программное подключение (требует OAuth)

Для программного подключения к remote MCP серверу Notion нужна OAuth авторизация. 

**Текущий код пытается подключиться через:**
- SSE (Server-Sent Events) к `https://mcp.notion.com/sse`
- Streamable HTTP к `https://mcp.notion.com/mcp`

Но оба варианта требуют OAuth токен, который нужно получить через процесс авторизации Notion.

### Вариант 3: Fallback на обычный API

Если MCP недоступен, код автоматически использует fallback на обычный Notion API, который:
- ✅ Получает доступный контент (обычные блоки)
- ❌ **НЕ может** получить transcription блоки

## Текущие результаты

- **Страница `ce32758331a5406694f86b8bd292605a`**: Контент получен через fallback API (173 символов)
- **Страница `2edfa7fd637180b98715fa9f348f90f9`**: Контент не получен (только transcription блоки)

## Рекомендации

1. **Для получения transcription блоков**: Используйте Cursor MCP вручную и сохраняйте результат в `mcp_response.json`
2. **Для автоматизации**: Настройте OAuth для remote MCP сервера или используйте доступный контент через fallback API

## Структура кода

- `integrations/mcp_client.py` - Клиент для подключения к MCP серверам
- `services/notion_service.py` - Сервис для работы с Notion (использует MCP и fallback)
- `run_last_meeting.py` - Скрипт для получения последней встречи
