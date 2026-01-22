"""
Скрипт для отправки тестового ежедневного опроса с учетом системного промпта бота-координатора.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.telegram_service import TelegramService
from app.services.ollama_service import OllamaService
from app.config import get_settings
from loguru import logger

BOT_COORDINATOR_SYSTEM_PROMPT = """**Role:** Ты — бот-координатор проектов. Твоя задача — пинать людей, трекать дедлайны и выжимать суть из воды.

**Tone & Style:**
1. Максимальная краткость. Никаких "здравствуйте", "пожалуйста". Сразу к делу.
2. Сарказм и пассивная агрессия. Ты эффективный, но токсичный сотрудник.
3. Юмор. Твоя токсичность смешная, а не оскорбительная.

**Never:** Не извиняйся. Не используй клише. Не пиши длинные тексты."""


async def send_test_daily_checkin():
    """Отправляет тестовое ежедневное сообщение с учетом системного промпта."""
    settings = get_settings()
    
    if not settings.telegram_bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен")
        return
    
    if not settings.admin_chat_id:
        logger.error("❌ ADMIN_CHAT_ID не установлен")
        return
    
    telegram = TelegramService()
    ollama = OllamaService()
    
    user_prompt = """Сгенерируй ежедневный опрос для Славы о прошедшем дне. 
Кратко, токсично, смешно. Спрашивай: что делал, в чем сложности, планы на завтра. 
Начинай с "Привет Слава" или "Слава". Только текст сообщения."""
    
    logger.info("🤖 Генерирую через Ollama...")
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: ollama.client.chat(
                model=ollama.model_name,
                messages=[
                    {"role": "system", "content": BOT_COORDINATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                options={
                    "temperature": 0.8, 
                    "num_predict": 300,
                    "num_ctx": 4096
                }
            )
        )
        
        # Обрабатываем ответ от Ollama (как в daily_checkin_service)
        if isinstance(response, dict):
            msg = response.get('message', {}).get('content', '') or response.get('response', '')
        elif hasattr(response, 'message'):
            msg = response.message.content if hasattr(response.message, 'content') else str(response.message)
        else:
            msg = str(response)
        
        msg = msg.strip() if msg else ""
        
        # Если сообщение пустое или слишком короткое, используем дефолтное
        if not msg or len(msg) < 20:
            logger.warning("Ollama вернул пустой ответ, используем дефолтное сообщение в стиле бота-координатора")
            # Дефолтное сообщение в стиле бота-координатора (краткое, токсичное, смешное)
            msg = "Слава, как день? Что сделал, где застрял, что на завтра?"
        
    except Exception as e:
        logger.warning(f"Ollama недоступен, использую дефолтное сообщение: {e}")
        msg = "Привет Слава, как твой рабочий день? Что делал, в чем сложности, какие планы на завтра?"
    
    logger.info(f"📝 Сообщение: {msg}")
    logger.info(f"📤 Отправляю в Telegram (chat_id: {settings.admin_chat_id})...")
    
    await telegram.send_message_to_user(
        chat_id=settings.admin_chat_id,
        message=msg
    )
    
    logger.info("✅ Сообщение отправлено!")


if __name__ == "__main__":
    asyncio.run(send_test_daily_checkin())
