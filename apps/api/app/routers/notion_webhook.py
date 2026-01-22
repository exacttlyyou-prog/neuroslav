"""
Роутер для обработки вебхуков от Notion.
При получении события page_updated из базы данных встреч,
автоматически запускает скрипт извлечения данных.
"""
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request, Header
from loguru import logger

router = APIRouter()

# Путь к корню проекта (от apps/api)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
EXTRACTOR_SCRIPT = PROJECT_ROOT / "apps" / "extractor" / "index.js"


def extract_page_id_from_event(event: Dict[str, Any]) -> Optional[str]:
    """
    Извлекает page_id из события вебхука Notion.
    
    Notion отправляет события в формате:
    {
        "object": "event",
        "entry": [
            {
                "id": "...",
                "object": "page",
                "created_time": "...",
                "last_edited_time": "...",
                "parent": {...},
                "properties": {...}
            }
        ]
    }
    """
    try:
        # Проверяем тип события
        if event.get("object") != "event":
            return None

        # Ищем entry с типом page
        entries = event.get("entry", [])
        for entry in entries:
            if entry.get("object") == "page":
                # ID страницы может быть в разных местах
                page_id = entry.get("id")
                if page_id:
                    return page_id
                
                # Или в parent
                parent = entry.get("parent")
                if parent and isinstance(parent, dict):
                    page_id = parent.get("page_id") or parent.get("database_id")
                    if page_id:
                        return page_id

        return None
    except Exception as e:
        logger.error(f"Ошибка при извлечении page_id из события: {e}")
        return None


@router.post("/webhook")
async def notion_webhook(
    request: Request,
    x_notion_signature: Optional[str] = Header(None, alias="x-notion-signature")
):
    """
    Обрабатывает POST-запросы от вебхука Notion.
    
    При получении события page_updated из базы данных встреч,
    автоматически запускает скрипт извлечения данных для этого page_id.
    
    Args:
        request: HTTP запрос с телом события
        x_notion_signature: Подпись запроса от Notion (для валидации, опционально)
    
    Returns:
        JSON ответ со статусом обработки
    """
    try:
        # Получаем тело запроса
        body = await request.json()
        
        logger.info("📥 Получен вебхук от Notion")
        logger.debug(f"Тело запроса: {json.dumps(body, indent=2, ensure_ascii=False)}")

        # Извлекаем page_id из события
        page_id = extract_page_id_from_event(body)
        
        if not page_id:
            logger.warning("⚠️  Не удалось извлечь page_id из события вебхука")
            # Возвращаем 200, чтобы Notion не повторял запрос
            return {
                "status": "ignored",
                "message": "Событие не содержит page_id или не является page_updated"
            }

        logger.info(f"📄 Извлечен page_id: {page_id}")

        # Проверяем наличие скрипта извлечения
        if not EXTRACTOR_SCRIPT.exists():
            logger.error(f"❌ Скрипт извлечения не найден: {EXTRACTOR_SCRIPT}")
            raise HTTPException(
                status_code=500,
                detail=f"Скрипт извлечения не найден: {EXTRACTOR_SCRIPT}"
            )

        # Запускаем скрипт извлечения в фоновом режиме
        logger.info(f"🚀 Запуск скрипта извлечения для page_id: {page_id}")
        
        try:
            # Запускаем скрипт через subprocess
            # Используем абсолютный путь к node и скрипту
            process = subprocess.Popen(
                [
                    "node",
                    str(EXTRACTOR_SCRIPT),
                    page_id
                ],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Не ждем завершения процесса (асинхронная обработка)
            # Логируем запуск
            logger.info(f"✅ Скрипт извлечения запущен (PID: {process.pid})")

            return {
                "status": "accepted",
                "message": f"Скрипт извлечения запущен для page_id: {page_id}",
                "page_id": page_id,
                "process_id": process.pid
            }

        except FileNotFoundError:
            logger.error("❌ Node.js не найден. Установите Node.js для работы скрипта извлечения.")
            raise HTTPException(
                status_code=500,
                detail="Node.js не установлен или не найден в PATH"
            )
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске скрипта извлечения: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка при запуске скрипта: {str(e)}"
            )

    except json.JSONDecodeError:
        logger.error("❌ Неверный формат JSON в теле запроса")
        raise HTTPException(status_code=400, detail="Неверный формат JSON")
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке вебхука: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhook/test")
async def test_webhook():
    """
    Тестовый endpoint для проверки работы вебхука.
    """
    return {
        "status": "ok",
        "message": "Вебхук-роутер работает",
        "extractor_script": str(EXTRACTOR_SCRIPT),
        "script_exists": EXTRACTOR_SCRIPT.exists()
    }
