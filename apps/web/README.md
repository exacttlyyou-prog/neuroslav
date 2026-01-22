# Digital Twin Web App

Frontend приложение для системы Digital Twin - персонального движка обработки задач, встреч и документов.

## Технологии

- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Shadcn/UI
- React Hook Form + Zod

## Установка

```bash
# Установить зависимости
npm install

# Запустить dev server
npm run dev
```

Приложение будет доступно по адресу http://localhost:3000

## Структура проекта

```
apps/web/
├── app/                    # Next.js App Router
│   ├── (tabs)/            # Группа роутов с табами
│   │   ├── tasks/         # Страница задач
│   │   ├── meetings/      # Страница встреч
│   │   └── context/       # Страница контекста/RAG
│   ├── api/               # API Routes
│   └── layout.tsx         # Root layout
├── components/
│   ├── ui/                # Shadcn/UI компоненты
│   ├── forms/             # Формы для каждого workflow
│   └── shared/            # Общие компоненты
├── lib/                    # Утилиты и конфиги
├── types/                  # TypeScript типы
└── public/               # Статические файлы
```

## Переменные окружения

Создайте файл `.env.local`:

```env
NEXT_PUBLIC_APP_URL=http://localhost:3000
OPENAI_API_KEY=your_key_here
```

## Разработка

- `npm run dev` - запуск dev server
- `npm run build` - сборка production версии
- `npm run lint` - проверка кода ESLint

## Статус

Phase 0 завершен. Базовая структура и UI готовы. API routes содержат заглушки для дальнейшей реализации workflows.
