# Архитектура: Чат с агентами

## Текущая архитектура (проблемы)

```
User → Выбор типа → Форма → Workflow → Результат
         ↑
    Нужно выбирать вручную
```

## Новая архитектура (решение)

```mermaid
flowchart TD
    User[Пользователь] --> Chat[Чат-интерфейс]
    Chat --> Router[AgentRouter]
    Router -->|классификация| LLM[Ollama LLM]
    LLM -->|intent| Router
    
    Router -->|task| TaskAgent[TaskAgent]
    Router -->|meeting| MeetingAgent[MeetingAgent]
    Router -->|message| MessageAgent[MessageAgent]
    Router -->|knowledge| KnowledgeAgent[KnowledgeAgent]
    Router -->|rag_query| RAGAgent[RAGAgent]
    Router -->|default| DefaultAgent[DefaultAgent]
    
    TaskAgent --> RAG[RAG Service]
    MeetingAgent --> RAG
    KnowledgeAgent --> RAG
    RAGAgent --> RAG
    
    RAG -->|контекст| TaskAgent
    RAG -->|контекст| MeetingAgent
    RAG -->|контекст| KnowledgeAgent
    
    TaskAgent --> TaskWorkflow[Task Workflow]
    MeetingAgent --> MeetingWorkflow[Meeting Workflow]
    KnowledgeAgent --> KnowledgeWorkflow[Knowledge Workflow]
    
    TaskWorkflow --> Notion[Notion]
    MeetingWorkflow --> Notion
    KnowledgeWorkflow --> Notion
    
    TaskWorkflow --> Telegram[Telegram]
    MeetingWorkflow --> Telegram
    
    TaskWorkflow --> DB[(SQLite)]
    MeetingWorkflow --> DB
    KnowledgeWorkflow --> DB
    
    TaskWorkflow -->|сохранить| RAG
    MeetingWorkflow -->|сохранить| RAG
    KnowledgeWorkflow -->|сохранить| RAG
    
    TaskAgent --> Response[Ответ в чат]
    MeetingAgent --> Response
    MessageAgent --> Response
    KnowledgeAgent --> Response
    RAGAgent --> Response
    DefaultAgent --> Response
    
    Response --> Chat
```

## Поток обработки сообщения

```mermaid
sequenceDiagram
    participant U as User
    participant C as Chat Interface
    participant R as AgentRouter
    participant L as LLM (Ollama)
    participant A as Agent
    participant G as RAG Service
    participant W as Workflow
    participant N as Notion/Telegram/DB
    
    U->>C: Вводит сообщение
    C->>R: POST /api/chat {message}
    R->>L: Классификация intent
    L-->>R: IntentClassification
    R->>A: Выбирает агента
    A->>G: Поиск контекста
    G-->>A: Похожий контент
    A->>W: Обработка с контекстом
    W->>N: Сохранение результатов
    W-->>A: Результат обработки
    A->>G: Сохранение в RAG
    A-->>R: AgentResponse
    R-->>C: Ответ с метаданными
    C-->>U: Отображение результата
```

## Компоненты системы

### Frontend

```
ChatInterface (главный)
├── MessageList (история)
│   └── MessageBubble (одно сообщение)
├── ChatInput (поле ввода)
├── QuickActions (быстрые действия)
│   ├── "Обработать последнюю встречу"
│   ├── "Мои задачи"
│   └── "Поиск по знаниям"
└── AgentBadge (индикатор агента)
```

### Backend

```
AgentRouter
├── classify() - классификация через LLM
└── route() - маршрутизация к агенту

Agents/
├── BaseAgent (базовый класс)
│   ├── get_rag_context()
│   ├── process()
│   └── save_to_rag()
├── TaskAgent
├── MeetingAgent
├── MessageAgent
├── KnowledgeAgent
├── RAGAgent
└── DefaultAgent
```

## Интеграция RAG

Каждый агент:
1. **Получает контекст** из RAG перед обработкой
2. **Использует контекст** для обогащения ответа
3. **Сохраняет результат** в RAG после обработки

```python
# Пример TaskAgent
async def process(self, user_input: str):
    # 1. Контекст из RAG
    similar_tasks = await self.rag.search_similar_tasks(user_input)
    
    # 2. Обработка с контекстом
    result = await self.task_workflow.process(
        user_input,
        context=similar_tasks
    )
    
    # 3. Сохранение в RAG
    await self.rag.add_task(result)
    
    return result
```

## Преимущества новой архитектуры

1. **Автоматизация** - не нужно выбирать тип действия
2. **Контекст** - каждый агент использует RAG
3. **Единый интерфейс** - один чат вместо множества форм
4. **Расширяемость** - легко добавить новых агентов
5. **Прозрачность** - видно какой агент обрабатывает
