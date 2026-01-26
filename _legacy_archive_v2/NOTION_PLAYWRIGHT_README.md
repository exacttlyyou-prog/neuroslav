# Скрипт автоматизации Notion через Playwright

## Описание

Скрипт автоматически открывает Notion в браузере, переходит на страницу встреч, находит последнюю встречу и извлекает её транскрипцию или саммари.

## Как работает

1. **Открытие браузера**: Использует профиль Chrome пользователя (где уже залогинен в Notion)
2. **Переход на страницу**: Открывает страницу встреч по `NOTION_MEETING_PAGE_ID`
3. **Прокрутка**: Прокручивает страницу до конца с динамической загрузкой контента
4. **Поиск последней встречи**: Ищет последнюю встречу по заголовкам с датами
5. **Извлечение контента**: Находит transcription или саммари блоки внутри последней встречи
6. **Возврат результата**: Возвращает контент для дальнейшей обработки

## Использование

### Через API

```bash
# Получить последнюю встречу
curl -X POST "http://localhost:8000/api/notion/last-meeting/auto?process=true"
```

### Через Python

```python
from app.services.notion_playwright_service import NotionPlaywrightService

service = NotionPlaywrightService()
result = await service.get_last_meeting_via_browser(page_id="your-page-id")

print(result["content"])  # Транскрипция или саммари
```

### Тестовый скрипт

```bash
cd apps/api
python -m app.scripts.test_notion_playwright
```

## Требования

1. **Playwright установлен**:
   ```bash
   pip install playwright
   playwright install chromium
   ```

2. **Авторизация в Notion**: 
   - Откройте Notion в Chrome и авторизуйтесь
   - Скрипт использует профиль Chrome, где вы уже залогинены

3. **Переменная окружения**:
   ```bash
   export NOTION_MEETING_PAGE_ID=your-page-id
   ```

## Алгоритм поиска контента

Скрипт использует несколько методов для поиска контента последней встречи:

1. **Поиск по структуре**: Ищет заголовки встреч (с датами) и собирает контент после них
2. **Поиск transcription блоков**: Ищет блоки с `data-block-type="transcription"` или классом `transcription`
3. **Поиск саммари**: Ищет блоки с текстом "саммари", "резюме", "summary"
4. **Fallback**: Если не найдено, берет последние большие блоки на странице

## Результат

Скрипт возвращает словарь:

```python
{
    "block_id": "id последнего блока",
    "block_type": "meeting" | "transcription" | "summary" | "fallback",
    "content": "Текст транскрипции или саммари",
    "title": "Заголовок встречи",
    "has_transcription": True/False,
    "has_summary": True/False
}
```

## Интеграция с чатом

Скрипт автоматически вызывается при команде "Обработай последнюю встречу" в чате:

```
Пользователь: "Обработай последнюю встречу"
  ↓
MeetingAgent → NotionPlaywrightService.get_last_meeting_via_browser()
  ↓
MeetingWorkflow.process_meeting(transcript=result["content"])
  ↓
Результат: саммари, участники, задачи
```

## Отладка

Если скрипт не работает:

1. Проверьте, что Playwright установлен: `playwright --version`
2. Проверьте авторизацию: откройте Notion в Chrome
3. Проверьте `NOTION_MEETING_PAGE_ID` в настройках
4. Запустите тестовый скрипт для диагностики
5. Проверьте логи: скрипт выводит подробные логи каждого шага

## Ограничения

- Работает только с Chrome (использует профиль Chrome)
- Требует авторизации в Notion через браузер
- Может быть медленным (зависит от скорости загрузки Notion)
- Notion может изменить структуру DOM, что потребует обновления селекторов
