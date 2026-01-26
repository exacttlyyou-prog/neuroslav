import asyncio
import sys
from pathlib import Path

# Добавляем путь к приложению
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.services.notion_extractor import notion_extractor
from app.services.telegram_service import TelegramService
from app.services.notion_service import NotionService
from app.config import get_settings
from loguru import logger

async def run_last_meeting():
    """
    Находит последнюю встречу в Notion, извлекает данные (AI Meeting Notes)
    и отправляет их в Telegram админу.
    """
    logger.info("🚀 Запуск процесса обработки последней встречи...")
    
    settings = get_settings()
    page_id = settings.notion_meeting_page_id
    
    if not page_id:
        logger.error("❌ NOTION_MEETING_PAGE_ID не установлен в .env")
        return

    try:
        # 1. Находим последний блок встречи
        logger.info(f"📥 Получение последнего блока со страницы {page_id}...")
        notion = NotionService()
        last_block = await notion.get_last_meeting_block(page_id)
        
        block_id = last_block.get("block_id")
        if not block_id:
            logger.error("❌ Не удалось найти блоки на странице встреч")
            return
            
        logger.info(f"✅ Найден последний блок встречи (ID: {block_id})")
        
        # 2. Извлекаем данные (Strategy A & B)
        logger.info("🧪 Извлечение AI Meeting Notes контента...")
        result = await notion_extractor.extract_data(block_id)
        
        if not result["success"]:
            logger.error(f"❌ Ошибка извлечения: {result.get('error')}")
            return
            
        logger.info(f"✅ Контент успешно извлечен (метод: {result.get('method')})")
        
        # 3. Отправляем в Telegram
        logger.info("📤 Отправка уведомления в Telegram...")
        telegram = TelegramService()
        
        message = f"<b>📋 Последняя встреча (AI Meeting Notes)</b>\n\n"
        message += f"📄 <b>Page ID:</b> <code>{block_id}</code>\n"
        message += f"🛠 <b>Метод извлечения:</b> <code>{result.get('method')}</code>\n\n"
        message += f"📝 <b>Контент:</b>\n{result['content']}"
        
        # Если сообщение слишком длинное для Telegram, обрезаем
        if len(message) > 4000:
            message = message[:3900] + "\n\n<i>... контент обрезан из-за ограничений Telegram ...</i>"
            
        await telegram.send_notification(message)
        logger.info("✨ Готово! Сообщение отправлено админу.")
        
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(run_last_meeting())
