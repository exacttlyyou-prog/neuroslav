# Инструкция по запуску

## Предварительные требования

1. **Ollama должен быть запущен:**
   ```bash
   ollama serve
   # Или проверьте, что сервис запущен
   curl http://localhost:11434/api/tags
   ```

2. **Установлены зависимости:**
   ```bash
   cd apps/api
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Настроен .env файл** (см. README.md)

## Запуск системы

### Терминал 1: FastAPI Backend
```bash
cd apps/api
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### Терминал 2: Next.js Frontend
```bash
cd apps/web
npm run dev
```

### Проверка работы

1. Backend: http://localhost:8000/health
2. Frontend: http://localhost:3000
3. API Docs: http://localhost:8000/docs

## Тестирование

### Создать задачу
```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"text": "Напомни мне про встречу в следующий вторник"}'
```

### Обработать встречу
```bash
curl -X POST http://localhost:8000/api/meetings/process \
  -F "transcript=Текст встречи здесь"
```

### Индексировать документ
```bash
curl -X POST http://localhost:8000/api/knowledge/index \
  -F "file=@document.pdf"
```
