# Notion AI Meeting Processor

Мульти-агентная система для автоматической обработки AI Meeting Notes в Notion.

## Архитектура

Система использует паттерн "Orchestrator-Workers" с тремя специализированными агентами:

- **Coordinator** (`coordinator.ts`) - главный цикл, опрашивает базу данных и управляет состоянием
- **Scraper Agent** (`agents/scraper.ts`) - извлекает контент через Playwright (обходит ограничения API)
- **Analyst Agent** (`agents/analyst.ts`) - анализирует текст через OpenAI и извлекает структурированные данные
- **Writer Agent** (`agents/writer.ts`) - создает задачи в Notion и обновляет страницы

## Установка

```bash
cd apps/agent-worker
npm install
```

## Настройка

1. Скопируйте `.env.example` в `.env` и заполните переменные:

```bash
cp .env.example .env
```

2. Настройте авторизацию Notion (создает `auth.json`):

```bash
npm run setup-auth
```

Следуйте инструкциям: откроется браузер, войдите в Notion, затем нажмите Enter в терминале.

## Запуск

### Development режим (с tsx):

```bash
npm run dev
```

### Production режим:

```bash
npm run build
npm start
```

## Конфигурация

Переменные окружения в `.env`:

- `NOTION_TOKEN` - токен интеграции Notion API
- `OPENAI_API_KEY` - ключ OpenAI API
- `NOTION_DB_ID` - ID базы данных со встречами
- `NOTION_TASKS_DB_ID` - ID базы данных с задачами
- `NOTION_STATUS_PROPERTY` - название свойства статуса (по умолчанию "Status")
- `POLL_INTERVAL` - интервал опроса в миллисекундах (по умолчанию 60000)

## Работа системы

1. Координатор периодически опрашивает базу данных Notion
2. Находит страницы со статусом "Ready to Process"
3. Для каждой страницы:
   - Обновляет статус на "Processing"
   - Scraper извлекает контент через Playwright
   - Analyst структурирует данные через OpenAI
   - Writer создает задачи и обновляет страницу
   - Обновляет статус на "Done" или "Error"

## Структура базы данных

### Meetings Database

Должна содержать свойство `Status` (или указанное в `NOTION_STATUS_PROPERTY`) типа Select со значениями:
- "Ready to Process"
- "Processing"
- "Done"
- "Error"

### Tasks Database

Должна содержать свойства для задач (названия могут отличаться, нужно адаптировать в `writer.ts`):
- `Name` (Title)
- `Description` (Rich Text, опционально)
- `Assignee` (Rich Text или People, опционально)
- `Due Date` (Date, опционально)
- `Priority` (Select, опционально)
