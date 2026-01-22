"""
Клиент для работы с Telegram Bot API.
"""
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from loguru import logger
from uuid import UUID

from core.config import get_settings
from core.schemas import MeetingAnalysis
from services.telegram_service import sanitize_html_for_telegram


class TelegramClient:
    """Клиент для отправки уведомлений в Telegram."""
    
    def __init__(self):
        settings = get_settings()
        if not settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")
        if not settings.admin_chat_id:
            raise ValueError("ADMIN_CHAT_ID не установлен в переменных окружения")
        self.bot = Bot(token=settings.telegram_bot_token)
        self.chat_id = settings.admin_chat_id
    
    async def send_analysis_notification(
        self,
        session_id: UUID,
        analysis: MeetingAnalysis,
        notion_page_url: str | None = None
    ) -> int:
        """
        Отправляет уведомление с результатами анализа и кнопками действий.
        
        Args:
            session_id: ID сессии для callback
            analysis: Результат анализа
            notion_page_url: Опциональная ссылка на страницу Notion
            
        Returns:
            ID отправленного сообщения
        """
        try:
            # Формируем сообщение в HTML формате (как генерирует ai_service)
            message_text = f"📋 <b>Анализ встречи</b>\n\n"
            summary_clean = sanitize_html_for_telegram(analysis.summary_md)
            message_text += f"{summary_clean}\n\n"
            
            if analysis.action_items:
                message_text += "<b>Задачи:</b>\n"
                for i, item in enumerate(analysis.action_items, 1):
                    assignee_text = f" ({item.assignee})" if item.assignee else ""
                    priority_emoji = {
                        'High': '🔴',
                        'Medium': '🟡',
                        'Low': '🟢'
                    }.get(item.priority, '⚪')
                    message_text += f"{i}. {priority_emoji} {item.text}{assignee_text}\n"
                message_text += "\n"
            
            if analysis.risk_assessment:
                message_text += f"⚠️ <b>Риски:</b> {analysis.risk_assessment}\n\n"
            
            if notion_page_url:
                message_text += f'<a href="{notion_page_url}">Открыть в Notion</a>'
            
            # Создаем клавиатуру с кнопками
            keyboard = [
                [
                    InlineKeyboardButton(
                        "✅ Одобрить и выполнить",
                        callback_data=f"approve:{session_id}"
                    ),
                    InlineKeyboardButton(
                        "❌ Отклонить",
                        callback_data=f"reject:{session_id}"
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем сообщение
            message = await self.bot.send_message(
                chat_id=self.chat_id,
                text=message_text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            
            logger.info(f"Отправлено уведомление в Telegram, message_id: {message.message_id}")
            return message.message_id
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления в Telegram: {e}")
            raise
    
    async def update_message(
        self,
        message_id: int,
        text: str,
        remove_keyboard: bool = True
    ) -> None:
        """
        Обновляет сообщение в Telegram.
        
        Args:
            message_id: ID сообщения для обновления
            text: Новый текст
            remove_keyboard: Удалить клавиатуру
        """
        try:
            # Очищаем HTML от неподдерживаемых тегов
            text = sanitize_html_for_telegram(text)
            
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=message_id,
                text=text,
                parse_mode='HTML'
            )
            
            logger.info(f"Обновлено сообщение {message_id} в Telegram")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении сообщения в Telegram: {e}")
            raise

