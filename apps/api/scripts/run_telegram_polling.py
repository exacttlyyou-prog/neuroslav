"""
Скрипт для запуска Telegram бота через polling (локальный режим).

Использование:
    cd "/Users/slava/Desktop/коллеги, обсудили"
    python apps/api/scripts/run_telegram_polling.py

Или из любой директории (скрипт автоматически найдет корень проекта):
    python /path/to/apps/api/scripts/run_telegram_polling.py

При первом сообщении автоматически инициализируются все сервисы:
- ContextLoader (загрузка контекста из Notion)
- NotionBackgroundParser (фоновый парсер страницы встреч)
- ProactiveService (проактивные действия)
- SchedulerService (планирование задач)
- Мониторинг производительности
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Добавляем путь к корню проекта
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(project_root))
# Добавляем путь к api приложению для корректных внутренних импортов (app.config и т.д.)
api_root = project_root / "apps" / "api"
sys.path.append(str(api_root))

# Загружаем переменные окружения
load_dotenv(project_root / ".env")

# Исправляем путь к БД, так как скрипт запускается из другой директории
# Если DATABASE_URL использует относительный путь, делаем его абсолютным относительно api_root
database_url = os.getenv("DATABASE_URL", "sqlite:///./data/digital_twin.db")
if "sqlite:///" in database_url and not database_url.startswith("sqlite:////"):
    # Относительный путь (./...)
    relative_path = database_url.split("sqlite:///")[1]
    if relative_path.startswith("./"):
        relative_path = relative_path[2:]
    
    # Если путь уже содержит apps/api, то оставляем как есть, иначе добавляем
    if "apps/api" not in relative_path:
        db_path = api_root / relative_path
    else:
        # Если запускаем из корня, а путь относительный внутри api
        db_path = project_root / relative_path
        
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    logger.info(f"🔧 Скорректирован путь к БД: {os.environ['DATABASE_URL']}")

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    from apps.api.app.routers.telegram_webhook import telegram_webhook, TelegramUpdate
    from apps.api.app.db.database import AsyncSessionLocal, init_db
    from apps.api.app.config import get_settings
except ImportError as e:
    logger.error(f"Ошибка импорта: {e}")
    logger.error("Убедитесь, что вы находитесь в виртуальном окружении и установлены все зависимости.")
    sys.exit(1)

# Глобальный флаг для отслеживания инициализации
_services_initialized = False
_initialization_in_progress = False

async def initialize_all_services():
    """
    Инициализирует все сервисы системы (аналог startup_event из main.py).
    Вызывается при первом сообщении или при старте.
    """
    global _services_initialized, _initialization_in_progress
    
    if _services_initialized:
        return
    
    if _initialization_in_progress:
        # Ждем завершения инициализации
        import asyncio
        for _ in range(100):  # Максимум 10 секунд ожидания
            await asyncio.sleep(0.1)
            if _services_initialized:
                return
        logger.warning("⚠️ Инициализация заняла слишком много времени, продолжаем...")
        return
    
    _initialization_in_progress = True
        
        logger.info("🚀 Инициализация всех сервисов...")
        settings = get_settings()
        
        # 1. Предзагрузка контекста из Notion
        try:
            from apps.api.app.services.context_loader import ContextLoader
            context_loader = ContextLoader()
            await context_loader.preload_context()
            logger.info("✅ Контекст предзагружен")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки контекста: {e}")
        
        # 2. Запуск фонового парсера Notion
        try:
            from apps.api.app.services.notion_background_parser import NotionBackgroundParser
            background_parser = NotionBackgroundParser()
            await background_parser.start()
            logger.info("✅ Фоновый парсер страницы встреч запущен")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось запустить фоновый парсер: {e}")
        
        # 3. Запуск ProactiveService
        try:
            from apps.api.app.services.proactive_service import get_proactive_service
            proactive_service = get_proactive_service()
            await proactive_service.start()
            logger.info("✅ ProactiveService запущен")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось запустить ProactiveService: {e}")
        
        # 4. Запуск SchedulerService
        try:
            from apps.api.app.services.scheduler_service import get_scheduler_service
            from apps.api.app.services.daily_checkin_service import DailyCheckinService
            from datetime import datetime, timedelta
            
            scheduler_service = get_scheduler_service()
            await scheduler_service.start()
            logger.info("✅ SchedulerService запущен")
            
            # Регистрируем ежедневную задачу на 18:30
            try:
                daily_checkin_service = DailyCheckinService()
                now = datetime.now()
                target_time = now.replace(hour=18, minute=30, second=0, microsecond=0)
                
                if now >= target_time:
                    target_time = target_time + timedelta(days=1)
                
                async def send_daily_checkin_task():
                    try:
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
                logger.info(f"✅ Ежедневный опрос запланирован на 18:30")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось зарегистрировать daily check-in задачу: {e}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось запустить SchedulerService: {e}")
        
        # 5. Проверка Notion API
        if settings.notion_token:
            try:
                from apps.api.app.services.notion_service import NotionService
                notion = NotionService()
                is_valid = await notion.validate_token()
                if is_valid:
                    logger.info("✅ Notion API доступен")
                    # Создаем необходимые базы данных
                    try:
                        init_status = await notion.ensure_required_databases()
                        logger.info("✅ Базы данных Notion готовы")
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка инициализации баз данных: {e}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка проверки Notion API: {e}")
        
        # 6. Проверка Telegram API
        if settings.telegram_bot_token:
            try:
                from apps.api.app.services.telegram_service import TelegramService
                telegram = TelegramService()
                is_valid = await telegram.validate_token()
                if is_valid:
                    logger.info("✅ Telegram API доступен")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка проверки Telegram API: {e}")
        
        # 7. Запуск мониторинга производительности
        try:
            from apps.api.app.core.monitoring import get_performance_monitor
            monitor = get_performance_monitor()
            monitor.start_background_collection()
            logger.info("✅ Мониторинг производительности запущен")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка запуска мониторинга: {e}")
        
        _services_initialized = True
        _initialization_in_progress = False
        logger.info("✅ Все сервисы инициализированы")
    except Exception as e:
        _initialization_in_progress = False
        logger.error(f"❌ Критическая ошибка при инициализации сервисов: {e}")
        raise

# Адаптер для вызова вебхука
async def process_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает обновление от Telegram, преобразуя его в формат вебхука
    и вызывая логику обработки.
    """
    try:
        # Инициализируем все сервисы при первом сообщении (lazy initialization)
        await initialize_all_services()
        
        # Преобразуем update в словарь, совместимый с Pydantic моделью TelegramUpdate
        update_dict = update.to_dict()
        
        # Создаем Pydantic модель
        telegram_update = TelegramUpdate(
            update_id=update.update_id,
            message=update_dict.get("message")
        )
        
        logger.info(f"Получено сообщение: {update.message.text if update.message else 'Нет текста'}")
        
        # Создаем сессию БД
        async with AsyncSessionLocal() as db:
            # Вызываем логику обработки вебхука
            # Примечание: telegram_webhook ожидает update и db
            result = await telegram_webhook(telegram_update, db)
            logger.info(f"Результат обработки: {result}")
            
    except Exception as e:
        logger.error(f"Ошибка при обработке обновления: {e}")

def main():
    """Запуск поллинга."""
    
    # Инициализируем базу данных
    # Делаем это синхронно через asyncio.run() в отдельной функции
    # Это предотвращает конфликты event loops
    def init_db_sync():
        try:
            logger.info("📦 Инициализация базы данных...")
            asyncio.run(init_db())
            logger.info("✅ База данных готова")
        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации БД: {e}")
            
    # Запускаем инициализацию (она создаст свой event loop, выполнит работу и закроет его)
    try:
        init_db_sync()
    except Exception:
        pass # Игнорируем ошибки (например, если loop уже есть), идем дальше

    settings = get_settings()
    token = settings.telegram_bot_token
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        return

    logger.info("🚀 Запуск Telegram Polling...")
    logger.info("Бот будет получать сообщения и обрабатывать их локально.")
    logger.info("Нажмите Ctrl+C для остановки.")
    logger.info("ℹ️ Сервисы будут инициализированы при первом сообщении")

    # Создаем приложение
    application = Application.builder().token(token).build()

    # Регистрируем обработчик для всех текстовых сообщений и команд
    application.add_handler(MessageHandler(filters.ALL, process_update))

    # Запускаем поллинг (синхронно)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Остановка поллинга")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
