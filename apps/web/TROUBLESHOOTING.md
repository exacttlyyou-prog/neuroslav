# Решение проблем

## Проблема: Страница не открывается (404)

### Решение 1: Очистить кеш Next.js

```bash
cd apps/web
rm -rf .next
npm run dev
```

### Решение 2: Переустановить зависимости

```bash
cd apps/web
rm -rf node_modules package-lock.json
npm install
npm run dev
```

### Решение 3: Проверить структуру роутов

Убедитесь, что файлы существуют:
- `app/(tabs)/tasks/page.tsx`
- `app/(tabs)/meetings/page.tsx`
- `app/(tabs)/context/page.tsx`
- `app/(tabs)/layout.tsx`

### Решение 4: Проверить порт

Если порт 3000 занят, измените в `package.json`:
```json
"dev": "next dev -p 3001"
```

## Проблема: Стили не применяются

Проверьте, что `app/globals.css` импортирован в `app/layout.tsx`:
```tsx
import "./globals.css"
```

## Проблема: Ошибки компиляции TypeScript

```bash
cd apps/web
npx tsc --noEmit
```

## Проблема: Компоненты не найдены

Проверьте path aliases в `tsconfig.json`:
```json
"paths": {
  "@/*": ["./*"]
}
```

## Логи и отладка

Проверьте логи dev server в терминале, где запущен `npm run dev`.

Если проблема сохраняется, проверьте:
1. Версию Node.js (должна быть 18+)
2. Версию npm
3. Консоль браузера (F12) на наличие ошибок
