"""
Подключение к базе данных SQLite.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from loguru import logger

from app.config import get_settings

settings = get_settings()

# Создаем async engine для SQLite
engine = create_async_engine(
    settings.database_url.replace("sqlite:///", "sqlite+aiosqlite:///"),
    echo=False,
    future=True
)

# Создаем session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()


async def get_db() -> AsyncSession:
    """
    Dependency для получения сессии БД.
    
    Yields:
        AsyncSession: Сессия базы данных
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Инициализация базы данных - создание таблиц и миграции."""
    async with engine.begin() as conn:
        # Создаем все таблицы
        await conn.run_sync(Base.metadata.create_all)
        
        # Миграция: добавляем колонку projects, если её нет
        try:
            # Проверяем, существует ли колонка projects
            result = await conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='meetings'")
            )
            table_sql = result.scalar()
            if table_sql and 'projects' not in table_sql:
                logger.info("Добавляем колонку projects в таблицу meetings...")
                await conn.execute(text("ALTER TABLE meetings ADD COLUMN projects JSON"))
                logger.info("Колонка projects добавлена")
        except Exception as e:
            logger.debug(f"Проверка/добавление колонки projects: {e}")
        
        # Миграция: добавляем колонку action_items, если её нет
        try:
            result = await conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='meetings'")
            )
            table_sql = result.scalar()
            if table_sql and 'action_items' not in table_sql:
                logger.info("Добавляем колонку action_items в таблицу meetings...")
                await conn.execute(text("ALTER TABLE meetings ADD COLUMN action_items JSON"))
                logger.info("Колонка action_items добавлена")
        except Exception as e:
            logger.debug(f"Проверка/добавление колонки action_items: {e}")
        
        # Миграция: добавляем колонки для расширенных данных саммари
        for column_name in ['key_decisions', 'insights', 'next_steps']:
            try:
                result = await conn.execute(
                    text("SELECT sql FROM sqlite_master WHERE type='table' AND name='meetings'")
                )
                table_sql = result.scalar()
                if table_sql and column_name not in table_sql:
                    logger.info(f"Добавляем колонку {column_name} в таблицу meetings...")
                    await conn.execute(text(f"ALTER TABLE meetings ADD COLUMN {column_name} JSON"))
                    logger.info(f"Колонка {column_name} добавлена")
            except Exception as e:
                logger.debug(f"Проверка/добавление колонки {column_name}: {e}")
        
        # Миграция: добавляем колонку telegram_chat_id в таблицу contacts, если её нет
        try:
            result = await conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='contacts'")
            )
            table_sql = result.scalar()
            if table_sql and 'telegram_chat_id' not in table_sql:
                logger.info("Добавляем колонку telegram_chat_id в таблицу contacts...")
                await conn.execute(text("ALTER TABLE contacts ADD COLUMN telegram_chat_id VARCHAR"))
                logger.info("Колонка telegram_chat_id добавлена")
        except Exception as e:
            logger.debug(f"Проверка/добавление колонки telegram_chat_id: {e}")
        
        # Миграция: добавляем колонки tov_style и is_active в таблицу contacts
        for column_name, column_type in [('tov_style', 'VARCHAR'), ('is_active', 'VARCHAR')]:
            try:
                result = await conn.execute(
                    text("SELECT sql FROM sqlite_master WHERE type='table' AND name='contacts'")
                )
                table_sql = result.scalar()
                if table_sql and column_name not in table_sql:
                    logger.info(f"Добавляем колонку {column_name} в таблицу contacts...")
                    await conn.execute(text(f"ALTER TABLE contacts ADD COLUMN {column_name} {column_type}"))
                    # Устанавливаем значения по умолчанию
                    if column_name == 'tov_style':
                        await conn.execute(text("UPDATE contacts SET tov_style = 'default' WHERE tov_style IS NULL"))
                    elif column_name == 'is_active':
                        await conn.execute(text("UPDATE contacts SET is_active = 'true' WHERE is_active IS NULL"))
                    logger.info(f"Колонка {column_name} добавлена")
            except Exception as e:
                logger.debug(f"Проверка/добавление колонки {column_name}: {e}")
    
    logger.info("База данных инициализирована")
