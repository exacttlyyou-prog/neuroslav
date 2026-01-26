"""
Скрипт для автоматической настройки Telegram webhook.
Использование:
    python apps/api/scripts/setup_telegram_webhook.py <webhook_url>
    
Пример:
    python apps/api/scripts/setup_telegram_webhook.py https://your-domain.com/api/telegram/webhook
"""
import asyncio
import sys
from pathlib import Path

# Добавляем путь к приложению
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root / "apps" / "api"))

from app.services.telegram_service import TelegramService
from app.config import get_settings
from loguru import logger

async def setup_webhook(webhook_url: str):
    """Настраивает webhook для Telegram бота."""
    try:
        settings = get_settings()
        if not settings.telegram_bot_token:
            logger.error("❌ TELEGRAM_BOT_TOKEN не установлен в .env")
            return False
        
        telegram = TelegramService()
        
        # Проверяем токен
        is_valid = await telegram.validate_token()
        if not is_valid:
            logger.error("❌ Токен бота невалиден")
            return False
        
        # Устанавливаем webhook
        logger.info(f"🔗 Настраиваю webhook: {webhook_url}")
        result = await telegram.bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"]
        )
        
        if result:
            logger.info("✅ Webhook успешно настроен!")
            
            # Проверяем текущий webhook
            webhook_info = await telegram.bot.get_webhook_info()
            logger.info(f"📋 Информация о webhook:")
            logger.info(f"   URL: {webhook_info.url}")
            logger.info(f"   Ожидает обновления: {webhook_info.pending_update_count}")
            
            return True
        else:
            logger.error("❌ Не удалось настроить webhook")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка при настройке webhook: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python setup_telegram_webhook.py <webhook_url>")
        print("Пример: python setup_telegram_webhook.py https://your-domain.com/api/telegram/webhook")
        sys.exit(1)
    
    webhook_url = sys.argv[1]
    success = asyncio.run(setup_webhook(webhook_url))
    sys.exit(0 if success else 1)
