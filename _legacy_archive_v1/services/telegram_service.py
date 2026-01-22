"""
Сервис для работы с Telegram Bot API.
"""
# Импорт telegram с fallback
try:
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    # Создаем заглушки
    Bot = None
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None
from loguru import logger
from uuid import UUID
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from core.config import get_settings
from core.schemas import MeetingAnalysis


def sanitize_html_for_telegram(html_text: str) -> str:
    """
    Очищает HTML от неподдерживаемых Telegram тегов.
    
    Telegram поддерживает только: <b>, <i>, <u>, <s>, <a>, <code>, <pre>, <blockquote>
    Удаляет: <li>, <ul>, <ol>, <p>, <div>, <span> и другие неподдерживаемые теги.
    
    Args:
        html_text: HTML текст для очистки
        
    Returns:
        Очищенный HTML текст, совместимый с Telegram
    """
    import re
    
    if not html_text:
        return ""
    
    text = html_text
    
    # КРИТИЧНО: Сначала удаляем все неподдерживаемые теги списков
    # Удаляем <ul> и </ul> полностью
    text = re.sub(r'<ul[^>]*>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'</ul>', '', text, flags=re.IGNORECASE)
    
    # Удаляем <ol> и </ol> полностью
    text = re.sub(r'<ol[^>]*>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'</ol>', '', text, flags=re.IGNORECASE)
    
    # Заменяем <li> на маркер, сохраняя содержимое
    text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
    
    # Удаляем другие неподдерживаемые теги, но сохраняем содержимое
    # Порядок важен - сначала сложные, потом простые
    unsupported_tags = [
        'p', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
        'br', 'hr', 'strong', 'em', 'table', 'tr', 'td', 'th', 
        'thead', 'tbody', 'tfoot', 'dl', 'dt', 'dd'
    ]
    
    for tag in unsupported_tags:
        # Удаляем открывающие теги с атрибутами
        text = re.sub(rf'<{tag}[^>]*>', '', text, flags=re.IGNORECASE | re.DOTALL)
        # Удаляем закрывающие теги
        text = re.sub(rf'</{tag}>', '', text, flags=re.IGNORECASE)
    
    # Заменяем <br> и <br/> на перенос строки (если еще остались)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    
    # Удаляем все оставшиеся HTML теги, кроме поддерживаемых Telegram
    # Поддерживаемые: b, i, u, s, a, code, pre, blockquote
    allowed_tags = ['b', 'i', 'u', 's', 'a', 'code', 'pre', 'blockquote']
    
    # Находим все теги
    tag_pattern = r'<(/)?([a-zA-Z][a-zA-Z0-9]*)[^>]*>'
    
    def replace_tag(match):
        closing = match.group(1)  # / если закрывающий тег
        tag_name = match.group(2).lower()
        
        if tag_name in allowed_tags:
            # Сохраняем поддерживаемый тег
            return match.group(0)
        else:
            # Удаляем неподдерживаемый тег
            return ''
    
    text = re.sub(tag_pattern, replace_tag, text, flags=re.IGNORECASE)
    
    # Нормализуем множественные переносы строк
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Убираем лишние пробелы в начале строк
    lines = text.split('\n')
    cleaned_lines = [line.lstrip() for line in lines]
    text = '\n'.join(cleaned_lines)
    
    # Финальная проверка - если остались какие-то теги <li>, <ul>, <ol>, удаляем их принудительно
    text = re.sub(r'<li[^>]*>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'</li>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<ul[^>]*>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'</ul>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<ol[^>]*>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'</ol>', '', text, flags=re.IGNORECASE)
    
    return text.strip()


class TelegramService:
    """Сервис для отправки уведомлений в Telegram."""
    
    def __init__(self, ai_service=None):
        settings = get_settings()
        if not settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")
        if not settings.admin_chat_id:
            raise ValueError("ADMIN_CHAT_ID не установлен в переменных окружения")
        self.bot = Bot(token=settings.telegram_bot_token)
        self.chat_id = settings.admin_chat_id
        self.ai_service = ai_service  # Для обогащения упоминаний
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
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
            summary_text = analysis.summary_md
            
            # Обогащаем упоминания людей ссылками перед отправкой
            if self.ai_service:
                summary_text = self.ai_service.enrich_mentions(summary_text)
            
            # Очищаем HTML от неподдерживаемых Telegram тегов
            summary_text = sanitize_html_for_telegram(summary_text)
            
            message_text += f"{summary_text}\n\n"
            
            if analysis.action_items:
                message_text += "<b>Задачи:</b>\n"
                for i, item in enumerate(analysis.action_items, 1):
                    assignee_text = f" ({item.assignee})" if item.assignee else ""
                    priority_emoji = {
                        'High': '🔴',
                        'Medium': '🟡',
                        'Low': '🟢'
                    }.get(item.priority, '⚪')
                    # Очищаем текст задачи от неподдерживаемых тегов
                    task_text_clean = sanitize_html_for_telegram(item.text)
                    assignee_clean = sanitize_html_for_telegram(assignee_text) if assignee_text else ""
                    message_text += f"{i}. {priority_emoji} {task_text_clean}{assignee_clean}\n"
                message_text += "\n"
            
            if analysis.risk_assessment:
                # Очищаем risk_assessment от неподдерживаемых тегов
                risk_clean = sanitize_html_for_telegram(analysis.risk_assessment)
                message_text += f"⚠️ <b>Риски:</b> {risk_clean}\n\n"
            
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
            
            # ФИНАЛЬНАЯ ЗАЩИТА: Очищаем весь message_text перед отправкой
            # Это гарантирует, что даже если где-то остались теги, они будут удалены
            message_text = sanitize_html_for_telegram(message_text)
            
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
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
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

