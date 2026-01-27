# Исправление ошибки деплоя на Vercel

## Проблема

Ошибка при деплое:
```
Failed to run "uv add --active -r /vercel/path0/requirements.txt"
No solution found when resolving dependencies for split
```

## Причина

1. Конфликт версий `langchain` и `langchain-core`
2. Vercel использует Python 3.14 вместо 3.11
3. Дубликат `httpx` в requirements.txt

## Исправления

### 1. Удалены все зависимости от langchain

**Проблема:** langchain требует Python 3.14, а Vercel использует Python 3.12.

**Решение:** 
- Создана собственная реализация `RecursiveCharacterTextSplitter` в `apps/api/app/utils/text_splitter.py`
- Удалены все зависимости: `langchain`, `langchain-core`, `langchain-text-splitters`, `langsmith`, `langgraph`
- Обновлен `knowledge_workflow.py` для использования собственного text splitter

### 2. Создан `.python-version`

Файл `.python-version` с версией `3.11` для явного указания версии Python в Vercel.

### 3. Создан `pyproject.toml`

Файл `pyproject.toml` для дополнительного указания версии Python.

### 2. Обновлен `apps/api/requirements.txt`

Те же исправления применены.

### 3. Упрощен `vercel.json`

Убрана конфигурация `functions` с `runtime`, так как Vercel автоматически определяет версию Python из `runtime.txt`.

## Что делать дальше

1. **Закоммить изменения:**
   ```bash
   git add requirements.txt apps/api/requirements.txt apps/api/app/utils/text_splitter.py apps/api/app/workflows/knowledge_workflow.py .python-version pyproject.toml
   git commit -m "Удаление langchain: замена на собственную реализацию text_splitter для совместимости с Vercel"
   git push
   ```

2. **Redeploy на Vercel:**
   - Зайди в Vercel Dashboard
   - Deployments → выбери последний деплой → Redeploy
   - Или подожди автоматического деплоя (если подключен GitHub)

3. **Проверь логи деплоя** в Vercel Dashboard

## Если проблема останется

Попробуй удалить тяжелые зависимости, которые не нужны для работы на Vercel:

- `playwright` - слишком тяжелый для serverless
- `chromadb` - может быть проблематичным
- `sentence-transformers` - очень тяжелый

Можно создать отдельный `requirements-vercel.txt` с минимальными зависимостями.
