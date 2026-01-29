"""
FastAPI приложение для Digital Twin System.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import tasks, meetings, knowledge, notion, chat, daily_checkin, telegram_webhook, notion_webhook, cache, monitoring, reports
from app.config import get_settings
from app.db.database import init_db
from loguru import logger
from app.core.logging_config import setup_production_logging

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

# Middleware для обработки ошибок и rate limiting
from app.core.middleware import ErrorHandlingMiddleware, RateLimitMiddleware
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(RateLimitMiddleware, calls_per_minute=120)  # 2 запроса в секунду

# Подключение роутеров
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(meetings.router, prefix="/api/meetings", tags=["meetings"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(notion.router, prefix="/api/notion", tags=["notion"])
app.include_router(notion_webhook.router, prefix="/api/notion", tags=["notion"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(daily_checkin.router, prefix="/api/daily-checkin", tags=["daily-checkin"])
app.include_router(telegram_webhook.router, prefix="/api/telegram", tags=["telegram"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(cache.router, prefix="/api/cache", tags=["cache"])
app.include_router(monitoring.router, prefix="/api/monitoring", tags=["monitoring"])


@app.on_event("startup")
async def startup_event():
    """Инициализация при старте приложения."""
    import os
    try:
        setup_production_logging()
    except Exception as e:
        logger.warning("⚠️ Логирование: %s", e)
    try:
        await init_db()
    except Exception as e:
        logger.warning("⚠️ init_db не удался (на Vercel нормально без БД для /health): %s", e)
    
    # Валидация токенов при старте
    import os
    _debug_log_path = os.environ.get("DEBUG_LOG_PATH")
    if _debug_log_path and os.path.isdir(os.path.dirname(_debug_log_path)):
        try:
            from datetime import datetime
            log_line = f'{{"sessionId":"debug-session","timestamp":{int(datetime.now().timestamp()*1000)},"location":"main.py: startup","message":"Starting server"}}\n'
            with open(_debug_log_path, "a") as f:
                f.write(log_line)
        except Exception:
            pass
    settings = get_settings()
    _is_vercel = os.environ.get("VERCEL") == "1"
    
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
                
                # Автоматически создаем необходимые базы данных
                logger.info("🔄 Проверка и создание необходимых баз данных в Notion...")
                try:
                    init_status = await notion.ensure_required_databases()
                    created_count = sum(1 for v in init_status.values() if v == "created")
                    existing_count = sum(1 for v in init_status.values() if v == "exists")
                    
                    if init_status["errors"]:
                        logger.warning(f"⚠️ Инициализация баз данных: {len(init_status['errors'])} ошибок")
                    else:
                        logger.info(f"✅ Базы данных готовы: {created_count} создано, {existing_count} существовало")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось автоматически создать базы данных: {e}")
                
                # Предзагружаем контекст только не на Vercel (serverless живёт запрос)
                if not _is_vercel:
                    try:
                        from app.services.context_loader import ContextLoader
                        context_loader = ContextLoader()
                        await context_loader.preload_context()
                        logger.info("✅ Контекст предзагружен для быстрого доступа")
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка предзагрузки контекста: {e}")
                
                # Мониторинг производительности — только не на Vercel
                if not _is_vercel:
                    try:
                        from app.core.monitoring import get_performance_monitor
                        monitor = get_performance_monitor()
                        monitor.start_background_collection()
                        logger.info("✅ Мониторинг производительности запущен")
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка запуска мониторинга: {e}")
                    
        except ValueError as e:
            logger.warning(f"⚠️ Не удалось инициализировать NotionService: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось проверить Notion API: {e}")
    else:
        logger.warning("⚠️ NOTION_TOKEN не установлен, функции Notion недоступны")
    
    # Проверка Telegram токена
    if settings.telegram_bot_token:
        try:
            logger.info("🔄 Проверка подключения к Telegram Bot API...")
            from app.services.telegram_service import TelegramService
            telegram = TelegramService()
            is_valid = await telegram.validate_token()
            if not is_valid:
                logger.warning("⚠️ Telegram API недоступен, отправка сообщений не будет работать")
            else:
                logger.info("✅ Telegram бот успешно подключен и готов к работе")
                
                # Автоматическая настройка webhook при старте (если указан URL)
                if settings.telegram_webhook_url:
                    try:
                        webhook_url = f"{settings.telegram_webhook_url.rstrip('/')}/api/telegram/webhook"
                        logger.info(f"🔗 Настраиваю Telegram webhook: {webhook_url}")
                        result = await telegram.bot.set_webhook(
                            url=webhook_url,
                            allowed_updates=["message", "callback_query"]
                        )
                        if result:
                            webhook_info = await telegram.bot.get_webhook_info()
                            logger.info(f"✅ Telegram webhook настроен: {webhook_info.url}")
                            logger.info(f"   Ожидает обновления: {webhook_info.pending_update_count}")
                        else:
                            logger.warning("⚠️ Не удалось настроить webhook автоматически")
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка при автоматической настройке webhook: {e}")
        except (ValueError, ImportError) as e:
            logger.warning(f"⚠️ Не удалось инициализировать TelegramService: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось проверить Telegram API: {e}")
    else:
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN не установлен, функции Telegram недоступны")
    
    # Фоновый парсер, ProactiveService, Scheduler — только не на Vercel (serverless нет долгоживущего процесса)
    if not _is_vercel:
        try:
            from app.services.notion_background_parser import NotionBackgroundParser
            background_parser = NotionBackgroundParser()
            await background_parser.start()
            app.state.background_parser = background_parser
            logger.info("✅ Фоновый парсер страницы встреч запущен")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось запустить фоновый парсер: {e}")
        
        try:
            from app.services.proactive_service import get_proactive_service
            proactive_service = get_proactive_service()
            await proactive_service.start()
            app.state.proactive_service = proactive_service
            logger.info("✅ ProactiveService запущен")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось запустить ProactiveService: {e}")
        
        try:
            from app.services.scheduler_service import get_scheduler_service
            from app.services.daily_checkin_service import DailyCheckinService
            from app.db.database import get_db
            scheduler_service = get_scheduler_service()
            await scheduler_service.start()
            app.state.scheduler_service = scheduler_service
            logger.info("✅ SchedulerService запущен")
            
            try:
                from datetime import datetime, timedelta
                daily_checkin_service = DailyCheckinService()
                now = datetime.now()
                target_time = now.replace(hour=18, minute=30, second=0, microsecond=0)
                if now >= target_time:
                    target_time = target_time + timedelta(days=1)
                
                async def send_daily_checkin_task():
                    try:
                        from app.db.database import AsyncSessionLocal
                        async with AsyncSessionLocal() as db:
                            result = await daily_checkin_service.send_daily_questions(db)
                            logger.info(f"Daily check-in отправлен: {result}")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке daily check-in: {e}")
                
                scheduler_service.schedule_task(
                    task_id="daily_checkin_1830",
                    execute_at=target_time,
                    action=send_daily_checkin_task,
                    action_args={},
                    repeat_interval=timedelta(days=1)
                )
                logger.info(f"✅ Ежедневный опрос запланирован на 18:30 (следующий запуск: {target_time})")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось зарегистрировать daily check-in задачу: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось запустить SchedulerService: {e}")
    else:
        logger.info("⏭ Vercel: фоновые сервисы (парсер, proactive, scheduler) пропущены")


@app.on_event("shutdown")
async def shutdown_event():
    """Остановка при выключении приложения."""
    if hasattr(app.state, "background_parser"):
        await app.state.background_parser.stop()
    if hasattr(app.state, "proactive_service"):
        await app.state.proactive_service.stop()
    if hasattr(app.state, "scheduler_service"):
        await app.state.scheduler_service.stop()


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Нейрослав API работает"}


@app.get("/health")
async def health():
    """Liveness: процесс жив."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    """Readiness: зависимости доступны, готов принимать webhook."""
    ok = True
    checks = {}
    try:
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = str(e)[:80]
        ok = False
    try:
        s = get_settings()
        checks["telegram_configured"] = bool(s.telegram_bot_token)
        checks["webhook_url"] = bool(s.telegram_webhook_url)
    except Exception as e:
        checks["config"] = str(e)[:80]
        ok = False
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ready" if ok else "degraded", "checks": checks}
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Глобальный обработчик исключений."""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )
