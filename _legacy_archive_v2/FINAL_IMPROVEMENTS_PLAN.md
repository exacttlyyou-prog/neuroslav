# Финальный план улучшений: Чат с агентами и автоматизация

## Критические проблемы

1. **AI саммари не подгружаются** - `summary_md` в markdown, но рендерится как HTML через `dangerouslySetInnerHTML`
2. **Дизайн фронта** - не автоматизирован, требует ручного выбора типа действия
3. **Архитектура** - отдельные workflows вместо единого чата с агентами
4. **RAG** - работает, но не интегрирован в общий поток

## Решение: Чат-интерфейс с агентами

### Концепция

Единый чат, где пользователь просто пишет, а система автоматически:
- Определяет тип сообщения (задача/встреча/знание/вопрос)
- Направляет к нужному агенту
- Обрабатывает с контекстом из RAG
- Сохраняет результаты автоматически

### Архитектура

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
RAG Context → Workflow → Notion → Telegram → БД
```

## Детальный план реализации

### Этап 1: Исправить проблему с саммари (КРИТИЧНО - 1-2 часа)

**Проблема:** `summary_md` в markdown, но рендерится через `dangerouslySetInnerHTML` как HTML

**Решение:**
1. Установить `react-markdown` для рендеринга markdown
2. Обновить `MeetingResults` компонент
3. Добавить fallback для пустых саммари

**Файлы:**
- `apps/web/package.json` - добавить `react-markdown`
- `apps/web/components/meetings/MeetingResults.tsx` - использовать `ReactMarkdown`
- `apps/web/components/meetings/MeetingAutoProcess.tsx` - исправить отображение саммари

### Этап 2: AgentRouter и классификация (Backend - 4-6 часов)

**Создать:**
- `apps/api/app/models/schemas.py` - добавить `IntentClassification`
- `apps/api/app/services/agent_router.py` - главный роутер
- `apps/api/app/services/agents/__init__.py`
- `apps/api/app/services/agents/base_agent.py` - базовый класс
- `apps/api/app/services/agents/task_agent.py`
- `apps/api/app/services/agents/meeting_agent.py`
- `apps/api/app/services/agents/knowledge_agent.py`
- `apps/api/app/services/agents/rag_agent.py`
- `apps/api/app/routers/chat.py` - API для чата

**IntentClassification:**
```python
class IntentClassification(BaseModel):
    agent_type: Literal["task", "meeting", "message", "knowledge", "rag_query", "default"]
    confidence: float
    extracted_data: Dict[str, Any]
    reasoning: str
```

**AgentRouter:**
```python
class AgentRouter:
    async def classify(self, user_input: str) -> IntentClassification:
        # LLM классификация через Ollama
        # Использует существующий OllamaService
```

**Агенты:**
- Каждый агент наследуется от `BaseAgent`
- Использует RAG для контекста перед обработкой
- Сохраняет результаты в RAG после обработки

### Этап 3: Чат-интерфейс (Frontend - 6-8 часов)

**Создать:**
- `apps/web/components/chat/ChatInterface.tsx` - главный компонент чата
- `apps/web/components/chat/MessageList.tsx` - список сообщений
- `apps/web/components/chat/MessageBubble.tsx` - одно сообщение
- `apps/web/components/chat/QuickActions.tsx` - быстрые действия
- `apps/web/components/chat/AgentBadge.tsx` - бейдж агента
- `apps/web/app/(tabs)/chat/page.tsx` - страница чата
- `apps/web/app/api/chat/route.ts` - API route

**Дизайн:**
- Чистый чат-интерфейс (стиль ChatGPT/Claude)
- История сообщений с индикаторами агентов
- Быстрые действия в боковой панели:
  - "Обработать последнюю встречу" (кнопка)
  - "Мои задачи"
  - "Поиск по знаниям"
- Автоматическое определение типа
- Real-time статус обработки (индикаторы)

**Обновить:**
- `apps/web/app/(tabs)/layout.tsx` - добавить вкладку "Чат"
- `apps/web/app/(tabs)/page.tsx` - редирект на `/chat`

### Этап 4: Интеграция RAG в агентов (2-3 часа)

**Обновить:**
- Все агенты используют `RAGService` для получения контекста
- `apps/api/app/services/rag_service.py` - добавить методы для агентов
- Каждый агент сохраняет результаты в RAG

**Поток:**
1. Агент получает запрос
2. Ищет похожий контент в RAG
3. Использует контекст для обработки
4. Сохраняет результат в RAG

### Этап 5: Улучшение дизайна (4-6 часов)

**Принципы:**
- Минимализм (Linear, Notion стиль)
- Автоматизация (меньше кликов)
- Прозрачность (видно что происходит)
- Быстрота (индикаторы загрузки)

**Обновления:**
- `apps/web/app/globals.css` - новая цветовая схема
- Улучшенная типографика
- Микро-интеракции
- Адаптивность для мобильных

## Технические детали

### AgentRouter классификация

```python
async def classify(self, user_input: str) -> IntentClassification:
    prompt = f"""
    Классифицируй сообщение пользователя. Типы:
    - task: задача с deadline или напоминание
    - meeting: репорт встречи, саммари встречи
    - message: отложенное сообщение для отправки
    - knowledge: сохранить информацию в базу знаний
    - rag_query: вопрос, поиск информации
    - default: общий ответ/помощь
    
    Сообщение: {user_input}
    """
    
    classification = await self.ollama.generate_structured(
        prompt, IntentClassification
    )
    return classification
```

### BaseAgent

```python
class BaseAgent:
    def __init__(self):
        self.rag = RAGService()
        self.context_loader = ContextLoader()
    
    async def process(self, user_input: str) -> AgentResponse:
        # 1. Получить контекст из RAG
        context = await self.rag.search_relevant(user_input)
        
        # 2. Обработать через workflow
        result = await self._process_with_context(user_input, context)
        
        # 3. Сохранить в RAG
        await self.rag.add_result(result)
        
        # 4. Вернуть ответ
        return result
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

## Порядок выполнения

1. **Срочно**: Исправить подгрузку саммари (markdown → HTML)
2. **Высокий**: Создать AgentRouter и базовые агенты
3. **Высокий**: Чат-интерфейс
4. **Средний**: Интеграция RAG в агентов
5. **Средний**: Улучшение дизайна

## Оценка времени

- Этап 1: 1-2 часа
- Этап 2: 4-6 часов
- Этап 3: 6-8 часов
- Этап 4: 2-3 часа
- Этап 5: 4-6 часов

**Итого: 17-25 часов работы**

## Результат

- Единый чат-интерфейс вместо отдельных форм
- Автоматическое определение типа сообщения
- Интеграция RAG в каждый агент
- Улучшенный дизайн
- Исправлена проблема с саммари
