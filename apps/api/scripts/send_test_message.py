"""
Скрипт для отправки тестового сообщения в Telegram.
"""
import asyncio
import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.telegram_service import TelegramService
from loguru import logger


async def send_test_message():
    """Отправляет тестовое сообщение админу."""
    try:
        telegram = TelegramService()
        
        # Проверяем токен
        is_valid = await telegram.validate_token()
        if not is_valid:
            logger.error("❌ Telegram токен невалиден")
            return
        
        # Отправляем тестовое сообщение
        message = (
            "🧪 <b>Тестовое сообщение</b>\n\n"
            "Это тестовое сообщение от бота Нейрослав.\n"
            "Если ты видишь это сообщение, значит всё работает! ✅"
        )
        
        message_id = await telegram.send_notification(message)
        logger.info(f"✅ Тестовое сообщение отправлено! Message ID: {message_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке сообщения: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(send_test_message())
