# Детальный план улучшений

## Проблемы

1. **Дизайн фронта** - не автоматизирован, требует ручного выбора
2. **AI саммари не подгружаются** - `summary_md` в markdown, но рендерится как HTML
3. **Архитектура** - отдельные workflows вместо единого чата
4. **RAG** - работает, но не интегрирован в общий поток

## Решение: Чат-интерфейс с агентами

### Архитектура агентов

```
User Input (чат)
    ↓
AgentRouter.classify() → IntentClassification
    ↓
┌───┴───┬──────┬──────────┬────────┬──────┐
│       │      │          │        │      │
Task  Meeting Message Knowledge  RAG  Default
Agent  Agent  Agent     Agent    Agent Agent
    ↓      ↓      ↓         ↓       ↓      ↓
Workflows → RAG Context → Notion → Telegram → БД
```

### Поток обработки

1. Пользователь пишет в чат
2. AgentRouter классифицирует через LLM
3. Выбранный агент:
   - Получает контекст из RAG
   - Обрабатывает через свой workflow
   - Сохраняет результаты
   - Возвращает ответ в чат

## План реализации

### Этап 1: Исправить проблему с саммари (срочно)

**Проблема:** `summary_md` в markdown формате, но рендерится через `dangerouslySetInnerHTML`

**Решение:**
1. Установить `react-markdown` или `marked`
2. Обновить `MeetingResults` для рендеринга markdown
3. Добавить fallback для пустых саммари

**Файлы:**
- `apps/web/components/meetings/MeetingResults.tsx` (обновить)
- `apps/web/package.json` (добавить `react-markdown`)

### Этап 2: AgentRouter (Backend)

**Файлы:**
- `apps/api/app/models/schemas.py` - добавить `IntentClassification`
- `apps/api/app/services/agent_router.py` (новый)
- `apps/api/app/services/agents/__init__.py` (новый)
- `apps/api/app/services/agents/base_agent.py` (новый)
- `apps/api/app/services/agents/task_agent.py` (новый)
- `apps/api/app/services/agents/meeting_agent.py` (новый)
- `apps/api/app/services/agents/knowledge_agent.py` (новый)
- `apps/api/app/services/agents/rag_agent.py` (новый)
- `apps/api/app/routers/chat.py` (новый)

**Функционал AgentRouter:**
```python
class AgentRouter:
    async def classify(self, user_input: str) -> IntentClassification:
        # LLM классификация через Ollama
        # Возвращает: agent_type, confidence, extracted_data
```

**Типы агентов:**
- `task` - задача (с deadline)
- `meeting` - репорт встречи
- `message` - отложенное сообщение
- `knowledge` - сохранить в базу знаний
- `rag_query` - поиск по знаниям
- `default` - общий ответ/помощь

### Этап 3: Чат-интерфейс (Frontend)

**Файлы:**
- `apps/web/components/chat/ChatInterface.tsx` (новый)
- `apps/web/components/chat/MessageList.tsx` (новый)
- `apps/web/components/chat/MessageBubble.tsx` (новый)
- `apps/web/components/chat/QuickActions.tsx` (новый)
- `apps/web/components/chat/AgentBadge.tsx` (новый)
- `apps/web/app/(tabs)/chat/page.tsx` (новый)
- `apps/web/app/api/chat/route.ts` (новый)

**Дизайн:**
- Чистый чат (как ChatGPT/Claude)
- История сообщений с индикаторами агентов
- Быстрые действия:
  - "Обработать последнюю встречу" (кнопка)
  - "Мои задачи"
  - "Поиск по знаниям"
- Автоматическое определение типа
- Real-time статус обработки

### Этап 4: Интеграция RAG в агентов

**Каждый агент:**
1. Получает контекст из RAG перед обработкой
2. Использует контекст для обогащения ответа
3. Сохраняет результаты в RAG после обработки

**Файлы:**
- Обновить все агенты для использования RAG
- `apps/api/app/services/rag_service.py` - добавить методы для агентов

### Этап 5: Улучшение дизайна

**Принципы:**
- Минимализм (Linear, Notion стиль)
- Автоматизация (меньше кликов)
- Прозрачность (видно что происходит)
- Быстрота (индикаторы загрузки)

**Обновления:**
- Новая цветовая схема
- Улучшенная типографика
- Микро-интеракции
- Адаптивность

## Технические детали

### IntentClassification Schema

```python
class IntentClassification(BaseModel):
    agent_type: Literal["task", "meeting", "message", "knowledge", "rag_query", "default"]
    confidence: float
    extracted_data: Dict[str, Any]
    reasoning: str
```

### BaseAgent

```python
class BaseAgent:
    async def process(self, user_input: str, context: List[str]) -> AgentResponse:
        # 1. Получить контекст из RAG
        # 2. Обработать через workflow
        # 3. Сохранить результаты
        # 4. Вернуть ответ
```

### Чат API

```typescript
POST /api/chat
{
  "message": "string",
  "history": Message[]
}

Response:
{
  "agent_type": "task" | "meeting" | ...,
  "response": "string",
  "actions": Action[],
  "metadata": {}
}
```

## Приоритеты

1. **Критично**: Исправить подгрузку саммари (markdown → HTML)
2. **Высокий**: Создать AgentRouter
3. **Высокий**: Чат-интерфейс
4. **Средний**: Интеграция RAG в агентов
5. **Средний**: Улучшение дизайна

## Оценка времени

- Этап 1: 1-2 часа
- Этап 2: 4-6 часов
- Этап 3: 6-8 часов
- Этап 4: 2-3 часа
- Этап 5: 4-6 часов

**Итого: 17-25 часов**
