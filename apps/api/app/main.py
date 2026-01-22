"""
FastAPI приложение для Digital Twin System.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import tasks, meetings, knowledge, notion, chat, daily_checkin, telegram_webhook, notion_webhook
from app.config import get_settings
from app.db.database import init_db
from loguru import logger

settings = get_settings()

app = FastAPI(
    title="Нейрослав API",
    description="API для обработки задач, встреч и документов",
    version="0.1.0"
)

# CORS для работы с Next.js Frontend
app.add_middleware(
    CORSMiddleware,
        allow_origins=["*"],  # Разрешаем все origins для Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(meetings.router, prefix="/api/meetings", tags=["meetings"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(notion.router, prefix="/api/notion", tags=["notion"])
app.include_router(notion_webhook.router, prefix="/api/notion", tags=["notion"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(daily_checkin.router, prefix="/api/daily-checkin", tags=["daily-checkin"])
app.include_router(telegram_webhook.router, prefix="/api/telegram", tags=["telegram"])


@app.on_event("startup")
async def startup_event():
    """Инициализация при старте приложения."""
    await init_db()
    
    # Валидация токенов при старте
    # #region agent log
    import os
    from datetime import datetime
    log_line = f'{{"sessionId":"debug-session","timestamp":{int(datetime.now().timestamp()*1000)},"location":"main.py: startup","message":"Starting server, checking env and modules","data":{{"PYTHONPATH":os.environ.get("PYTHONPATH"),"cwd":os.getcwd(),"settings_notion":bool(settings.notion_token)}}}}\n'
    with open("/Users/slava/Desktop/коллеги, обсудили/.cursor/debug.log", "a") as f:
        f.write(log_line)
    # #endregion
    settings = get_settings()
    
    # Проверка Notion токена
    if settings.notion_token:
        try:
            from app.services.notion_service import NotionService
            notion = NotionService()
            is_valid = await notion.validate_token()
            if not is_valid:
                logger.warning("⚠️ Notion API недоступен, некоторые функции могут не работать")
            else:
                logger.info("✅ Notion API доступен и токен валиден")
        except ValueError as e:
            logger.warning(f"⚠️ Не удалось инициализировать NotionService: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось проверить Notion API: {e}")
    else:
        logger.warning("⚠️ NOTION_TOKEN не установлен, функции Notion недоступны")
    
    # Проверка Telegram токена
    if settings.telegram_bot_token:
        try:
            from app.services.telegram_service import TelegramService
            telegram = TelegramService()
            is_valid = await telegram.validate_token()
            if not is_valid:
                logger.warning("⚠️ Telegram API недоступен, отправка сообщений не будет работать")
            else:
                logger.info("✅ Telegram API доступен и токен валиден")
        except (ValueError, ImportError) as e:
            logger.warning(f"⚠️ Не удалось инициализировать TelegramService: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось проверить Telegram API: {e}")
    else:
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN не установлен, функции Telegram недоступны")
    
    # Запуск фонового парсера для страницы "встречи альфа 2026"
    try:
        from app.services.notion_background_parser import NotionBackgroundParser
        background_parser = NotionBackgroundParser()
        await background_parser.start()
        # Сохраняем ссылку на парсер для доступа из других мест
        app.state.background_parser = background_parser
        logger.info("✅ Фоновый парсер страницы встреч запущен")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось запустить фоновый парсер: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Остановка при выключении приложения."""
    if hasattr(app.state, "background_parser"):
        await app.state.background_parser.stop()


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Нейрослав API работает"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/notion/parser/status")
async def get_parser_status():
    """Возвращает статус фонового парсера страницы встреч."""
    if hasattr(app.state, "background_parser"):
        return app.state.background_parser.get_status()
    return {"running": False, "error": "Парсер не инициализирован"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Глобальный обработчик исключений."""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )
