import asyncio
import sys
from pathlib import Path
from loguru import logger
from sqlalchemy import select, delete

# Добавляем путь к корню проекта
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(project_root))
# Добавляем путь к api приложению для корректных внутренних импортов (app.config и т.д.)
api_root = project_root / "apps" / "api"
sys.path.append(str(api_root))

# Загружаем переменные окружения (чтобы подтянулись настройки)
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# Исправляем путь к БД
import os
database_url = os.getenv("DATABASE_URL", "sqlite:///./data/digital_twin.db")
if "sqlite:///" in database_url and not database_url.startswith("sqlite:////"):
    relative_path = database_url.split("sqlite:///")[1]
    if relative_path.startswith("./"):
        relative_path = relative_path[2:]
    
    # Строим абсолютный путь к файлу БД
    db_path = api_root / relative_path
    
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    logger.info(f"🔧 Скорректирован путь к БД: {os.environ['DATABASE_URL']}")

from apps.api.app.db.database import AsyncSessionLocal
from apps.api.app.db.models import Task

async def cleanup_tasks():
    """Удаляет задачи, содержащие технический мусор от LLM."""
    logger.info("🧹 Начинаю очистку задач от мусора...")
    
    async with AsyncSessionLocal() as session:
        try:
            # 1. Ищем задачи, текст которых начинается с "model=" (типичная ошибка repr() модели Ollama)
            # Используем ilike для регистронезависимого поиска
            stmt = select(Task).where(Task.text.ilike("model=%"))
            result = await session.execute(stmt)
            tasks = result.scalars().all()
            
            count = len(tasks)
            if count == 0:
                logger.info("✅ Мусорных задач не найдено.")
                return

            logger.info(f"Найдено {count} мусорных задач. Пример: {tasks[0].text[:50]}...")
            logger.info("Удаляю...")
            
            # Удаляем
            delete_stmt = delete(Task).where(Task.text.ilike("model=%"))
            await session.execute(delete_stmt)
            await session.commit()
            
            logger.info(f"✅ Успешно удалено {count} задач.")
            
        except Exception as e:
            logger.error(f"Ошибка при очистке: {e}")
            await session.rollback()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(cleanup_tasks())
