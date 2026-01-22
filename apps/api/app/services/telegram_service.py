"""
Сервис для работы с Telegram Bot API.
"""
from typing import Optional, List, Dict

try:
    from telegram import Bot
    # В версии 22.x User не нужен для базовой функциональности
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Bot = None  # type: ignore

from loguru import logger
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from app.config import get_settings


def sanitize_html_for_telegram(html_text: str) -> str:
    """
    Очищает HTML от неподдерживаемых Telegram тегов.
    
    Telegram поддерживает только: <b>, <i>, <u>, <s>, <a>, <code>, <pre>, <blockquote>
    Удаляет: <li>, <ul>, <ol>, <p>, <div>, <span>, <h1>-<h6>, <strong>, <em> и другие неподдерживаемые теги.
    """
    import re
    
    if not html_text:
        return ""
    
    text = html_text
    
    # КРИТИЧНО: Заменяем <br> и <br/> на перенос строки ПЕРВЫМ (до других замен)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    
    # Удаляем неподдерживаемые теги списков
    text = re.sub(r'<ul[^>]*>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'</ul>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<ol[^>]*>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'</ol>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)
    text = re.sub(r'</li>', '\n', text, flags=re.IGNORECASE)
    
    # Удаляем заголовки (h1-h6)
    text = re.sub(r'<h[1-6][^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</h[1-6]>', '\n\n', text, flags=re.IGNORECASE)
    
    # Заменяем <strong> и <em> на поддерживаемые теги
    text = re.sub(r'<strong[^>]*>', '<b>', text, flags=re.IGNORECASE)
    text = re.sub(r'</strong>', '</b>', text, flags=re.IGNORECASE)
    text = re.sub(r'<em[^>]*>', '<i>', text, flags=re.IGNORECASE)
    text = re.sub(r'</em>', '</i>', text, flags=re.IGNORECASE)
    
    # Удаляем другие неподдерживаемые теги
    text = re.sub(r'<p[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<div[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<span[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</span>', '', text, flags=re.IGNORECASE)
    
    # Удаляем другие распространенные неподдерживаемые теги
    text = re.sub(r'<section[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</section>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<article[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</article>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<header[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</header>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<footer[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</footer>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<nav[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</nav>', '\n', text, flags=re.IGNORECASE)
    
    # Удаляем теги таблиц (Telegram не поддерживает)
    text = re.sub(r'<table[^>]*>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'</table>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<tr[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</tr>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<td[^>]*>', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'</td>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<th[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</th>', '', text, flags=re.IGNORECASE)
    
    # Удаляем все остальные HTML теги, кроме поддерживаемых Telegram
    # Поддерживаемые: <b>, <i>, <u>, <s>, <a>, <code>, <pre>, <blockquote>
    allowed_tags = ['b', 'i', 'u', 's', 'a', 'code', 'pre', 'blockquote']
    # Удаляем все теги, которые не в списке разрешенных
    def remove_unallowed_tags(match):
        tag = match.group(1).lower()
        if tag not in allowed_tags:
            return ''
        return match.group(0)
    
    # Удаляем все закрывающие теги, которые не в списке разрешенных
    text = re.sub(r'</([^>]+)>', lambda m: '</' + m.group(1) + '>' if m.group(1).lower() in allowed_tags else '', text, flags=re.IGNORECASE)
    
    # Очищаем множественные переносы строк
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Удаляем лишние пробелы в начале и конце строк
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    return text.strip()


class TelegramService:
    """Сервис для работы с Telegram Bot API."""
    
    def __init__(self):
        if not TELEGRAM_AVAILABLE or Bot is None:
            raise ImportError("python-telegram-bot не установлен. Установите: pip install python-telegram-bot")
        
        settings = get_settings()
        if not settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")
        
        # Проверка формата токена (формат: числа:буквы)
        if ":" not in settings.telegram_bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN не содержит ':', возможно неверный формат (ожидается: числа:буквы)")
        
        # Bot гарантированно не None здесь, т.к. мы проверили TELEGRAM_AVAILABLE
        assert Bot is not None, "Bot class must be available"
        self.bot: Bot = Bot(token=settings.telegram_bot_token)
        self.admin_chat_id = settings.admin_chat_id
        self.ok_chat_id = settings.ok_chat_id
    
    async def validate_token(self) -> bool:
        """
        Проверяет, что TELEGRAM_BOT_TOKEN валиден и API доступен.
        
        Returns:
            True если токен валиден, False иначе
        """
        try:
            me = await self.bot.get_me()
            logger.info(f"✅ TELEGRAM_BOT_TOKEN валиден, бот: @{me.username} (ID: {me.id})")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if "unauthorized" in error_msg or "401" in error_msg:
                logger.error("❌ Telegram API: Неверный токен (401). Проверьте TELEGRAM_BOT_TOKEN в .env")
            else:
                logger.error(f"❌ TELEGRAM_BOT_TOKEN невалиден или API недоступен: {e}")
            return False
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def send_notification(self, message: str, parse_mode: str = "HTML") -> int:
        """
        Отправляет уведомление админу.
        
        Args:
            message: Текст сообщения
            parse_mode: Режим парсинга (HTML или Markdown)
            
        Returns:
            ID отправленного сообщения
        """
        try:
            # Очищаем HTML для Telegram
            if parse_mode == "HTML":
                message = sanitize_html_for_telegram(message)
            
            result = await self.bot.send_message(
                chat_id=self.admin_chat_id,
                text=message,
                parse_mode=parse_mode
            )
            
            logger.info(f"Уведомление отправлено в Telegram: {result.message_id}")
            return result.message_id
        except Exception as e:
            error_msg = str(e).lower()
            if "unauthorized" in error_msg or "401" in error_msg:
                logger.error("❌ Telegram API: Неверный токен (401). Проверьте TELEGRAM_BOT_TOKEN")
                raise ValueError("Неверный TELEGRAM_BOT_TOKEN") from e
            elif "bad request" in error_msg or "400" in error_msg:
                logger.error(f"❌ Telegram API: Неверный запрос (400): {e}")
                raise
            else:
                logger.error(f"Ошибка при отправке уведомления в Telegram: {e}")
                raise
    
    async def send_task_reminder(self, task_text: str, deadline: Optional[str] = None) -> int:
        """
        Отправляет напоминание о задаче.
        
        Args:
            task_text: Текст задачи
            deadline: Deadline задачи (опционально)
            
        Returns:
            ID отправленного сообщения
        """
        message = f"<b>Напоминание о задаче:</b>\n\n{task_text}"
        if deadline:
            message += f"\n\n<b>Deadline:</b> {deadline}"
        
        return await self.send_notification(message)
    
    async def send_meeting_draft(self, draft_message: str) -> int:
        """
        Отправляет draft follow-up сообщения после встречи.
        
        Args:
            draft_message: Текст draft сообщения
            
        Returns:
            ID отправленного сообщения
        """
        message = f"<b>Draft follow-up сообщения:</b>\n\n{draft_message}"
        return await self.send_notification(message)
    
    async def send_to_ok_chat(self, message: str, parse_mode: str = "HTML") -> Optional[int]:
        """
        Отправляет сообщение в OK чат (если настроен).
        
        Args:
            message: Текст сообщения
            parse_mode: Режим парсинга (HTML или Markdown)
            
        Returns:
            ID отправленного сообщения или None, если OK чат не настроен
        """
        if not self.ok_chat_id:
            logger.warning("OK_CHAT_ID не установлен, пропускаем отправку на OK")
            return None
        
        try:
            if parse_mode == "HTML":
                message = sanitize_html_for_telegram(message)
            
            result = await self.bot.send_message(
                chat_id=self.ok_chat_id,
                text=message,
                parse_mode=parse_mode
            )
            
            logger.info(f"Сообщение отправлено в OK чат: {result.message_id}")
            return result.message_id
        except Exception as e:
            logger.error(f"Ошибка при отправке в OK чат: {e}")
            raise
    
    async def send_meeting_summary(
        self,
        summary: str,
        action_items: Optional[List] = None,
        participants: Optional[List] = None,
        send_to_ok: bool = True,
        send_to_admin: bool = True
    ) -> Dict[str, Optional[int]]:
        """
        Отправляет саммари встречи в Telegram (на OK и/или админу).
        
        Args:
            summary: Саммари встречи
            action_items: Список задач (опционально)
            participants: Список участников (опционально)
            send_to_ok: Отправлять ли на OK
            send_to_admin: Отправлять ли админу
            
        Returns:
            Словарь с ID отправленных сообщений:
            {
                "ok_message_id": int | None,
                "admin_message_id": int | None
            }
        """
        # Формируем сообщение
        message = f"<b>📋 Саммари встречи</b>\n\n"
        
        if participants:
            message += f"<b>Участники:</b> {', '.join([p.get('name', str(p)) if isinstance(p, dict) else str(p) for p in participants])}\n\n"
        
        # Очищаем summary от неподдерживаемых HTML тегов (особенно <br>)
        summary_clean = sanitize_html_for_telegram(summary)
        message += f"{summary_clean}\n\n"
        
        if action_items:
            message += "<b>Задачи:</b>\n"
            for i, item in enumerate(action_items[:10], 1):  # Первые 10 задач
                if isinstance(item, dict):
                    priority_emoji = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}.get(item.get('priority', 'Medium'), '⚪')
                    assignee_text = f" ({item.get('assignee', '')})" if item.get('assignee') else ""
                    message += f"{i}. {priority_emoji} {item.get('text', '')}{assignee_text}\n"
                else:
                    message += f"{i}. {str(item)}\n"
            
            if len(action_items) > 10:
                message += f"\n... и еще {len(action_items) - 10} задач\n"
        
        message += "\n"
        
        result = {
            "ok_message_id": None,
            "admin_message_id": None
        }
        
        # Отправляем на OK (если нужно)
        if send_to_ok:
            try:
                ok_id = await self.send_to_ok_chat(message)
                result["ok_message_id"] = ok_id
            except Exception as e:
                logger.error(f"Ошибка при отправке на OK: {e}")
        
        # Отправляем админу (если нужно)
        if send_to_admin:
            try:
                admin_id = await self.send_notification(message)
                result["admin_message_id"] = admin_id
            except Exception as e:
                logger.error(f"Ошибка при отправке админу: {e}")
        
        return result
    
    async def send_meeting_minutes(
        self,
        summary: str,
        action_items: Optional[List] = None,
        participants: Optional[List] = None,
        send_to_admin: bool = True,
        send_to_participants: bool = True
    ) -> Dict[str, Any]:
        """
        Отправляет минутки встречи в Telegram с тегами участников.
        
        Args:
            summary: Саммари встречи
            action_items: Список задач (опционально)
            participants: Список участников (опционально)
            send_to_admin: Отправлять ли админу (по умолчанию True)
            send_to_participants: Отправлять ли всем участникам (по умолчанию True)
            
        Returns:
            Словарь с ID отправленных сообщений:
            {
                "admin_message_id": int | None,
                "participants": [
                    {"name": str, "chat_id": str, "message_id": int | None, "error": str | None}
                ]
            }
        """
        # Формируем сообщение
        message = f"<b>📋 Минутки встречи</b>\n\n"
        
        if participants:
            # Формируем список участников с тегами
            participants_list = []
            for p in participants:
                if isinstance(p, dict):
                    name = p.get('name', '')
                    username = p.get('telegram_username', '')
                    if username:
                        participants_list.append(f"@{username}")
                    else:
                        participants_list.append(name)
                else:
                    participants_list.append(str(p))
            
            if participants_list:
                message += f"<b>Участники:</b> {', '.join(participants_list)}\n\n"
        
        # Очищаем summary от неподдерживаемых HTML тегов
        summary_clean = sanitize_html_for_telegram(summary)
        message += f"{summary_clean}\n\n"
        
        if action_items:
            message += "<b>Задачи:</b>\n"
            for i, item in enumerate(action_items[:10], 1):  # Первые 10 задач
                if isinstance(item, dict):
                    priority_emoji = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}.get(item.get('priority', 'Medium'), '⚪')
                    assignee = item.get('assignee', '')
                    
                    # Ищем telegram_username для ответственного
                    assignee_tag = ""
                    if assignee and participants:
                        assignee_lower = assignee.lower().strip()
                        for p in participants:
                            if isinstance(p, dict):
                                p_name = p.get('name', '').lower().strip()
                                p_username = p.get('telegram_username', '')
                                original_name = p.get('original_name', '').lower().strip()
                                matched_name = p.get('matched_name', '').lower().strip()
                                
                                # Сравниваем имя ответственного с участником (разные варианты)
                                if (assignee_lower == p_name or 
                                    assignee_lower == original_name or 
                                    assignee_lower == matched_name or
                                    assignee_lower in p_name or 
                                    p_name in assignee_lower):
                                    if p_username:
                                        assignee_tag = f" @{p_username}"
                                    else:
                                        assignee_tag = f" ({p.get('name', assignee)})"
                                    break
                    
                    if not assignee_tag and assignee:
                        assignee_tag = f" ({assignee})"
                    
                    message += f"{i}. {priority_emoji} {item.get('text', '')}{assignee_tag}\n"
                else:
                    message += f"{i}. {str(item)}\n"
            
            if len(action_items) > 10:
                message += f"\n... и еще {len(action_items) - 10} задач\n"
        
        message += "\n"
        
        result = {
            "admin_message_id": None,
            "participants": []
        }
        
        # Отправляем админу (если нужно)
        if send_to_admin:
            try:
                admin_id = await self.send_notification(message)
                result["admin_message_id"] = admin_id
                logger.info(f"✅ Минутки отправлены админу: {admin_id}")
            except Exception as e:
                logger.error(f"Ошибка при отправке минуток админу: {e}")
        
        # Отправляем всем участникам с telegram_chat_id или telegram_username
        if send_to_participants and participants:
            for participant in participants:
                if not isinstance(participant, dict):
                    continue
                
                name = participant.get('name', 'Неизвестно')
                chat_id = participant.get('telegram_chat_id')
                username = participant.get('telegram_username')
                
                participant_result = {
                    "name": name,
                    "chat_id": chat_id,
                    "message_id": None,
                    "error": None
                }
                
                # Пробуем отправить по chat_id (приоритет)
                if chat_id:
                    try:
                        message_id = await self.send_message_to_user(
                            chat_id=str(chat_id),
                            message=message,
                            parse_mode="HTML"
                        )
                        participant_result["message_id"] = message_id
                        logger.info(f"✅ Минутки отправлены участнику {name} (chat_id: {chat_id}): {message_id}")
                    except Exception as e:
                        error_msg = str(e)
                        participant_result["error"] = error_msg
                        logger.warning(f"⚠️ Не удалось отправить минутки участнику {name} (chat_id: {chat_id}): {error_msg}")
                elif username:
                    # Если есть только username, но нет chat_id, логируем предупреждение
                    # В будущем можно добавить поиск chat_id по username через базу контактов
                    participant_result["error"] = f"У участника {name} есть telegram_username (@{username}), но нет telegram_chat_id. Нужно добавить chat_id в базу контактов."
                    logger.warning(f"⚠️ У участника {name} нет telegram_chat_id, только username: @{username}")
                else:
                    participant_result["error"] = f"У участника {name} нет telegram_chat_id и telegram_username"
                    logger.debug(f"Участник {name} не имеет telegram_chat_id или telegram_username, пропускаем")
                
                result["participants"].append(participant_result)
        
        return result
    
    async def send_message_to_user(
        self,
        chat_id: str,
        message: str,
        parse_mode: Optional[str] = None
    ) -> int:
        """
        Отправляет сообщение конкретному пользователю по chat_id.
        
        Args:
            chat_id: Chat ID пользователя
            message: Текст сообщения
            parse_mode: Режим парсинга (HTML, Markdown или None)
            
        Returns:
            ID отправленного сообщения
        """
        try:
            if parse_mode == "HTML":
                message = sanitize_html_for_telegram(message)
            
            result = await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=parse_mode
            )
            
            logger.info(f"Сообщение отправлено пользователю {chat_id}: {result.message_id}")
            return result.message_id
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения пользователю {chat_id}: {e}")
            raise
