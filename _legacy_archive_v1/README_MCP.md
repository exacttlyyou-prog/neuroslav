# MCP Notion Integration - Надежный способ получения контента

## Проблема

Обычный Notion API не может читать блоки `meeting-notes`, которые содержат транскрипции встреч. Для чтения таких блоков требуется MCP Notion.

## Решение

Использование MCP Notion через Cursor для получения полного контента страниц с meeting-notes блоками.

## Быстрый старт

### 1. Получение данных через MCP

```bash
# Получить данные страницы через MCP
python get_mcp_content.py --get
```

Затем вставьте JSON ответ от MCP Notion.

### 2. Тестирование контента

```bash
# Проверить, что контент корректно извлечен
python get_mcp_content.py --test
```

### 3. Запуск анализа

```bash
# Анализ последней встречи с использованием MCP данных
python run_last_meeting.py
```

## Ручной способ получения MCP данных

Если автоматический способ не работает:

1. В терминале Cursor выполните:
```bash
curl -X POST http://localhost:3000/mcp/notion/fetch \
  -H "Content-Type: application/json" \
  -d '{"id": "2edfa7fd637180b98715fa9f348f90f9"}'
```

2. Скопируйте JSON ответ
3. Сохраните в файл `mcp_response.json`
4. Запустите `python run_last_meeting.py`

## Структура данных

MCP Notion возвращает:
- `<meeting-notes>` блоки с транскрипциями
- Последний блок = самая свежая встреча
- Содержит `<summary>`, `<transcript>`, `<notes>` секции

## Автоматизация

Для полной автоматизации добавьте в cron или планировщик:

```bash
# Ежечасно проверять новые встречи
0 * * * * cd /path/to/project && python run_last_meeting.py
```

## Файлы

- `run_last_meeting.py` - основной скрипт анализа
- `get_mcp_content.py` - получение данных через MCP
- `mcp_response.json` - кэшированные MCP данные
- `MCP_INSTRUCTIONS.md` - подробные инструкции

## Устранение проблем

### ChromaDB ошибка
```bash
rm -rf db/
python run_last_meeting.py
```

### Пустой контент
- Убедитесь, что MCP данные актуальные
- Проверьте, что страница содержит meeting-notes блоки
- Используйте `python get_mcp_content.py --test`

### Telegram не работает
- Установите `pip install python-telegram-bot`
- Проверьте токен бота в `.env`