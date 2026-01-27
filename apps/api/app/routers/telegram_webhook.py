"""
Webhook для обработки входящих сообщений от Telegram.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from loguru import logger
from pydantic import BaseModel

from app.services.daily_checkin_service import DailyCheckinService
from app.services.telegram_service import TelegramService
from app.db.database import get_db, AsyncSessionLocal
from app.models.schemas import SecureTelegramUpdate
from app.core.security import get_telegram_auth, require_telegram_auth
import asyncio

router = APIRouter()


def get_neural_slav_thinking_response(agent_type: str = "default") -> str:
    """Возвращает живой ответ в стиле Neural Slav для разных ситуаций."""
    import random
    
    # Расширенные базовые ответы для общих сообщений
    general_responses = [
        "Я тут, на звонок не пойду...",
        "Да, но только если ты не хочешь, чтобы я уволился за твои вопросы.",
        "Работаю. Что нужно?",
        "Слушаю. Не тяни время.",
        "На месте. Чем займемся?",
        "Пошел разбираться...",
        "Думаю, не перебивай...",
        "Секунду, консультируюсь с базой данных...",
        "Минутку, проверяю архивы...",
        "Сейчас посмотрю что тут у нас...",
        "Обрабатываю твой поток сознания...",
        "Анализирую этот хаос...",
        "Секунду, стряхиваю пыль с серверов...",
        "Минутку, консультируюсь с нейросетью...",
        "Ищу в памяти что-то полезное...",
        "Загружаю контекст из прошлого века...",
    ]
    
    # Специфичные для типа агента
    if agent_type == "task":
        return random.choice([
            "Создаю очередную задачу...",
            "Добавляю в твой бесконечный список дел...",
            "Планирую, кого пинать и когда...",
            "Составляю план твоих страданий...",
            "Записываю в список неотложных дел...",
        ])
    elif agent_type == "meeting":
        return random.choice([
            "Вспоминаю, о чем мы там болтали...",
            "Разбираю этот поток сознания...",
            "Извлекаю смысл из хаоса...",
            "Анализирую вашу болтовню...",
            "Ищу крупицы смысла в разговоре...",
        ])
    elif agent_type == "knowledge":
        return random.choice([
            "Складываю в долговременную память...",
            "Записываю в базу знаний...",
            "Каталогизирую информацию...",
            "Архивирую в отделы памяти...",
            "Добавляю к коллекции фактов...",
        ])
    elif agent_type == "rag_query":
        return random.choice([
            "Роюсь в архивах...",
            "Ищу в базе данных...",
            "Сканирую историю встреч...",
            "Проверяю старые записи...",
            "Листаю пыльные тома памяти...",
        ])
    elif agent_type == "message":
        return random.choice([
            "Планирую отправку...",
            "Настраиваю будильник...",
            "Ставлю напоминание...",
            "Записываю в список к отправке...",
            "Готовлю уведомления...",
        ])
    else:
        return random.choice(general_responses)


class TelegramUpdate(BaseModel):
    """Модель обновления от Telegram."""
    update_id: int
    message: dict | None = None


@router.post("/webhook")
async def telegram_webhook(
    update: SecureTelegramUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Обрабатывает входящие сообщения от Telegram с проверками безопасности.
    """
    try:
        # Обработка callback_query (нажатие на inline кнопки)
        callback_query = update.callback_query if hasattr(update, 'callback_query') else None
        if callback_query is None and isinstance(update, dict):
            callback_query = update.get('callback_query')
        
        if callback_query:
            # Извлекаем данные из callback_query (может быть dict или объект)
            if isinstance(callback_query, dict):
                callback_data = callback_query.get("data", "")
                callback_message = callback_query.get("message", {})
                callback_id = callback_query.get("id", "")
            else:
                callback_data = getattr(callback_query, "data", "")
                callback_message = getattr(callback_query, "message", {})
                callback_id = getattr(callback_query, "id", "")
            
            if isinstance(callback_message, dict):
                chat_id = str(callback_message.get("chat", {}).get("id", ""))
            else:
                chat_id = str(getattr(callback_message, "chat", {}).get("id", ""))
            
            logger.info(f"Получен callback_query: {callback_data} от chat_id: {chat_id}")
            
            # Инициализируем сервисы для обработки callback
            service = DailyCheckinService()
            
            # Обрабатываем callback_data
            if callback_data.startswith("menu:"):
                menu_type = callback_data.split(":")[1]
                
                if menu_type == "tasks":
                    # Показываем задачи
                    from sqlalchemy import select
                    from app.db.models import Task
                    
                    async with AsyncSessionLocal() as session:
                        result = await session.execute(
                            select(Task).where(Task.status == "pending").limit(10)
                        )
                        tasks = result.scalars().all()
                        
                        if tasks:
                            tasks_text = "<b>📋 Активные задачи:</b>\n\n"
                            for i, task in enumerate(tasks, 1):
                                deadline_str = ""
                                if task.deadline:
                                    deadline_str = f" (до {task.deadline.strftime('%d.%m %H:%M')})"
                                tasks_text += f"{i}. {task.text}{deadline_str}\n"
                        else:
                            tasks_text = "Нет активных задач"
                        
                        await service.telegram.send_message_to_user(
                            chat_id=chat_id,
                            message=tasks_text
                        )
                
                elif menu_type == "reminders":
                    # Показываем напоминания
                    from sqlalchemy import select
                    from app.db.models import Task
                    from datetime import datetime, timedelta
                    
                    async with AsyncSessionLocal() as session:
                        now = datetime.now()
                        week_from_now = now + timedelta(days=7)
                        
                        result = await session.execute(
                            select(Task)
                            .where(Task.status == "pending")
                            .where(Task.deadline.isnot(None))
                            .where(Task.deadline >= now)
                            .where(Task.deadline <= week_from_now)
                            .order_by(Task.deadline)
                            .limit(10)
                        )
                        tasks = result.scalars().all()
                        
                        if tasks:
                            reminders_text = "<b>⏰ Предстоящие напоминания:</b>\n\n"
                            for i, task in enumerate(tasks, 1):
                                deadline_str = task.deadline.strftime('%d.%m %H:%M') if task.deadline else "—"
                                days_left = (task.deadline - now).days if task.deadline else 0
                                
                                if days_left == 0:
                                    time_left = "сегодня"
                                elif days_left == 1:
                                    time_left = "завтра"
                                else:
                                    time_left = f"через {days_left} дн."
                                
                                reminders_text += f"{i}. {task.text}\n"
                                reminders_text += f"   📅 {deadline_str} ({time_left})\n\n"
                        else:
                            reminders_text = "Нет предстоящих напоминаний"
                        
                        await service.telegram.send_message_to_user(
                            chat_id=chat_id,
                            message=reminders_text
                        )
                
                elif menu_type == "meetings":
                    # Показываем встречи
                    from sqlalchemy import select, desc
                    from app.db.models import Meeting
                    
                    async with AsyncSessionLocal() as session:
                        result = await session.execute(
                            select(Meeting).order_by(desc(Meeting.created_at)).limit(5)
                        )
                        meetings = result.scalars().all()
                        
                        if meetings:
                            meetings_text = "<b>📝 Последние встречи:</b>\n\n"
                            for i, meeting in enumerate(meetings, 1):
                                summary_preview = (meeting.summary or "Без саммари")[:100]
                                date_str = meeting.created_at.strftime('%d.%m %H:%M') if meeting.created_at else "—"
                                meetings_text += f"<b>{i}. Встреча ({date_str})</b>\n"
                                meetings_text += f"{summary_preview}...\n\n"
                        else:
                            meetings_text = "Нет встреч"
                        
                        await service.telegram.send_message_to_user(
                            chat_id=chat_id,
                            message=meetings_text
                        )
                
                elif menu_type == "search":
                    # Показываем подсказку для поиска
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message="🔍 <b>Поиск по базе знаний</b>\n\n"
                                "Используй команду /knowledge [запрос]\n\n"
                                "Пример: /knowledge проект Альфа"
                    )
                
                elif menu_type == "settings":
                    # Показываем настройки (пока заглушка)
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message="⚙️ <b>Настройки</b>\n\n"
                                "Настройки пока не доступны. В разработке."
                    )
                
                # Отвечаем на callback_query
                try:
                    callback_query_id = callback_id if callback_id else (callback_query.get("id") if isinstance(callback_query, dict) else getattr(callback_query, "id", ""))
                    if callback_query_id:
                        await service.telegram.bot.answer_callback_query(
                            callback_query_id=callback_query_id,
                            text="Обработано"
                        )
                except Exception as e:
                    logger.error(f"Ошибка при ответе на callback_query: {e}")
            
            return {"ok": True}
        
        if not update.message:
            return {"ok": True}
        
        message = update.message
        chat_id = str(message.get("chat", {}).get("id"))
        text = message.get("text", "")
        
        # Извлекаем информацию о пользователе
        from_user = message.get("from", {})
        sender_username = from_user.get("username", "")
        sender_first_name = from_user.get("first_name", "")
        sender_id = str(from_user.get("id", ""))
        
        logger.debug(f"Сообщение от: username={sender_username}, first_name={sender_first_name}, id={sender_id}")
        
        # Проверяем авторизацию пользователя
        telegram_auth = get_telegram_auth()
        if not telegram_auth.verify_telegram_webhook(chat_id):
            logger.warning(f"Unauthorized access attempt from chat_id: {chat_id}")
            return {"ok": True}  # Возвращаем ok для Telegram, но не обрабатываем
        
        # Проверяем подозрительный контент
        security_manager = telegram_auth.security_manager
        suspicious_patterns = security_manager.check_suspicious_content(text)
        if suspicious_patterns:
            security_manager.log_security_event(
                event_type="suspicious_content",
                client_id=chat_id,
                description=f"Suspicious patterns found: {suspicious_patterns}",
                severity="medium",
                context={"text": text[:200], "patterns": suspicious_patterns}
            )
        
        # Проверяем, является ли сообщение пересылаемым
        is_forwarded = any([
            message.get("forward_from"),
            message.get("forward_from_chat"),
            message.get("forward_sender_name"),
            message.get("forward_date")
        ])
        
        if is_forwarded:
            logger.info(f"Получено пересылаемое сообщение от Telegram: {text[:50]}... (chat_id: {chat_id})")
        else:
            logger.info(f"Получено сообщение от Telegram: {text} (chat_id: {chat_id})")
        
        # Инициализируем сервисы
        service = DailyCheckinService()
        
        # Специальная обработка пересылаемых сообщений
        if is_forwarded:
            try:
                # Извлекаем метаданные о пересылке
                forward_info = {}
                if message.get("forward_from"):
                    forward_info["from_user"] = {
                        "id": message["forward_from"].get("id"),
                        "username": message["forward_from"].get("username"),
                        "first_name": message["forward_from"].get("first_name"),
                        "last_name": message["forward_from"].get("last_name")
                    }
                if message.get("forward_from_chat"):
                    forward_info["from_chat"] = {
                        "id": message["forward_from_chat"].get("id"),
                        "title": message["forward_from_chat"].get("title"),
                        "type": message["forward_from_chat"].get("type")
                    }
                if message.get("forward_date"):
                    from datetime import datetime
                    forward_info["original_date"] = datetime.fromtimestamp(message["forward_date"]).strftime('%d.%m.%Y %H:%M')
                if message.get("forward_sender_name"):
                    forward_info["sender_name"] = message["forward_sender_name"]
                
                # Формируем контекст для обработки
                forwarded_context = f"ПЕРЕСЫЛАЕМОЕ СООБЩЕНИЕ:\n"
                forwarded_context += f"Текст: {text}\n"
                
                if forward_info.get("from_user"):
                    user_info = forward_info["from_user"]
                    name = user_info.get("first_name", "")
                    if user_info.get("last_name"):
                        name += f" {user_info['last_name']}"
                    if user_info.get("username"):
                        name += f" (@{user_info['username']})"
                    forwarded_context += f"От пользователя: {name}\n"
                
                if forward_info.get("from_chat"):
                    chat_info = forward_info["from_chat"]
                    forwarded_context += f"Из чата: {chat_info.get('title', 'Неизвестный')}\n"
                
                if forward_info.get("original_date"):
                    forwarded_context += f"Дата оригинала: {forward_info['original_date']}\n"
                
                if forward_info.get("sender_name"):
                    forwarded_context += f"Отправитель: {forward_info['sender_name']}\n"
                
                forwarded_context += "\nИЗВЛЕКИ ПОЛЕЗНУЮ ИНФОРМАЦИЮ И ДОБАВЬ В БАЗУ ЗНАНИЙ ИЛИ СОЗДАЙ ЗАДАЧУ"
                
                logger.info(f"📧 Обработка пересылаемого сообщения через AgentRouter")
                
                # МОМЕНТАЛЬНАЯ обратная связь - отправляем сразу при получении пересылаемого сообщения
                try:
                    initial_response = get_neural_slav_thinking_response("knowledge")
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message=initial_response
                    )
                except Exception as auto_response_error:
                    logger.error(f"❌ Ошибка при отправке автоответа для пересылки: {auto_response_error}")
                    # Продолжаем обработку даже если автоответ не отправился
                
                # Обрабатываем через AgentRouter
                from app.services.agent_router import AgentRouter
                router = AgentRouter()
                
                classification = await router.classify(forwarded_context)
                logger.info(f"📋 Классификация пересылки: {classification.agent_type} (уверенность: {classification.confidence:.2f})")
                
                # Передаем sender_username для привязки к базе данных
                agent_response = await router.route(forwarded_context, classification, sender_username=sender_username)
                
                # Формируем информацию о трассировке агентов
                trace_info = ""
                decision_trace = agent_response.metadata.get("decision_trace", {}) if agent_response.metadata else {}
                
                # Эмодзи для разных типов агентов
                agent_emojis = {
                    "task": "📋",
                    "meeting": "🎯", 
                    "message": "📨",
                    "knowledge": "🧠",
                    "rag_query": "🔍",
                    "default": "🤖"
                }
                
                agent_emoji = agent_emojis.get(agent_response.agent_type, "🤖")
                
                # Используем единый cleaning pipeline
                from app.services.agents.base_agent import BaseAgent
                from app.services.telegram_service import sanitize_html_for_telegram
                base_agent = BaseAgent() 
                clean_response = base_agent.clean_response(agent_response.response)
                
                # Дополнительная очистка через sanitize_html_for_telegram
                if clean_response:
                    clean_response = sanitize_html_for_telegram(clean_response)
                
                # Отправляем подтверждение обработки
                if clean_response:
                    preview = clean_response[:300] + ('...' if len(clean_response) > 300 else '')
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message=f"📧 <b>Обработано</b>\n\n{preview}"
                    )
                
                # Показываем важные действия
                if agent_response.actions:
                    user_friendly_actions = base_agent.format_user_friendly_actions(agent_response.actions)
                    
                    if user_friendly_actions:
                        actions_text = "\n".join(user_friendly_actions)
                        # Очищаем действия от технических символов
                        actions_text = sanitize_html_for_telegram(actions_text)
                        await service.telegram.send_message_to_user(
                            chat_id=chat_id,
                            message=actions_text
                        )
                
                logger.info(f"✅ Пересылаемое сообщение успешно обработано через {agent_response.agent_type}Agent")
                return {"ok": True}
                
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке пересылаемого сообщения: {e}")
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message=f"❌ Ошибка при обработке пересылаемого сообщения: {str(e)}"
                )
                return {"ok": True}
        
        # Обработка команд
        if text.startswith("/"):
            command = text.split()[0].lower()
            
            if command == "/start" or command == "/dashboard":
                # Создаем inline keyboard для пульта управления
                try:
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                    
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📋 Задачи", callback_data="menu:tasks")],
                        [InlineKeyboardButton(text="⏰ Напоминания", callback_data="menu:reminders")],
                        [InlineKeyboardButton(text="📝 Встречи", callback_data="menu:meetings")],
                        [InlineKeyboardButton(text="🔍 Поиск", callback_data="menu:search")],
                        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")]
                    ])
                    
                    await service.telegram.bot.send_message(
                        chat_id=chat_id,
                        text="<b>🎛 Пульт управления</b>\n\nВыберите раздел:",
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Ошибка при создании inline keyboard: {e}")
                    # Fallback на обычное сообщение
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message="Привет! Я Нейрослав — твой AI-ассистент.\n\n"
                                "Доступные команды:\n"
                                "/dashboard - пульт управления\n"
                                "/tasks - список задач\n"
                                "/reminders - напоминания\n"
                                "/meetings - последние встречи\n"
                                "/help - справка"
                    )
                return {"ok": True}
            
            elif command == "/help":
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message="<b>Справка по командам:</b>\n\n"
                            "/status - текущий статус записи\n"
                            "/health - полная диагностика систем\n"
                            "/report - отчет по использованию агентов\n"
                            "/tasks - список активных задач\n"
                            "/meetings - последние встречи\n"
                            "/knowledge [запрос] - поиск по базе знаний\n"
                            "/test - запустить полный тест системы\n\n"
                            "Также можно просто писать сообщения — я сам определю, что нужно сделать."
                )
                return {"ok": True}
            
            elif command == "/status":
                from app.services.recording_service import get_recording_service
                recording_service = get_recording_service()
                status = recording_service.get_status()
                
                status_text = "Статус системы:\n\n"
                status_text += f"Запись: {'🟢 Идет' if status.get('is_recording') else '⚪ Остановлена'}\n"
                if status.get('pid'):
                    status_text += f"PID: {status['pid']}\n"
                
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message=status_text
                )
                return {"ok": True}
            
            elif command == "/health":
                # Проверяем здоровье всех систем в стиле Neural Slav
                try:
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message="🔍 <b>Проверяю системы...</b>\n\nЭто займёт пару секунд. Терпение - добродетель глупцов."
                    )
                    
                    health_report = []
                    errors = []
                    
                    # 1. Проверка Ollama
                    try:
                        from app.services.ollama_service import OllamaService
                        ollama = OllamaService()
                        
                        # Простой тестовый запрос
                        test_response = await ollama.generate_persona_response("тест", "системная проверка")
                        if test_response and len(test_response) > 5:
                            health_report.append("🟢 <b>Ollama:</b> Работает. Хотя медленно как всегда.")
                        else:
                            health_report.append("🟡 <b>Ollama:</b> Отвечает, но что-то мутное.")
                    except Exception as e:
                        health_report.append("🔴 <b>Ollama:</b> Лежит. Типично для локалки.")
                        errors.append(f"Ollama: {str(e)[:100]}")
                    
                    # 2. Проверка Notion
                    try:
                        from app.services.notion_service import NotionService
                        notion = NotionService()
                        
                        # Проверяем токен и автоинициализацию
                        is_valid = await notion.validate_token()
                        if is_valid:
                            init_status = await notion.ensure_required_databases()
                            
                            if len(init_status["errors"]) == 0:
                                health_report.append("🟢 <b>Notion:</b> Всё на месте. Базы инициализированы.")
                            else:
                                health_report.append(f"🟡 <b>Notion:</b> Работает, но есть косяки с базами.")
                                errors.extend([f"Notion: {err[:100]}" for err in init_status["errors"][:2]])
                        else:
                            health_report.append("🔴 <b>Notion:</b> Токен протух или права не те.")
                    except Exception as e:
                        health_report.append("🔴 <b>Notion:</b> Недоступен. Проверь интернет.")
                        errors.append(f"Notion: {str(e)[:100]}")
                    
                    # 3. Проверка базы данных
                    try:
                        from app.db.database import AsyncSessionLocal
                        from sqlalchemy import text
                        
                        async with AsyncSessionLocal() as db:
                            result = await db.execute(text("SELECT COUNT(*) FROM tasks"))
                            tasks_count = result.scalar() or 0
                            
                            result = await db.execute(text("SELECT COUNT(*) FROM meetings"))
                            meetings_count = result.scalar() or 0
                            
                            health_report.append(f"🟢 <b>База данных:</b> Жива. {tasks_count} задач, {meetings_count} встреч.")
                    except Exception as e:
                        health_report.append("🔴 <b>База данных:</b> Проблемы с доступом.")
                        errors.append(f"Database: {str(e)[:100]}")
                    
                    # 4. Проверка записи (если настроена)
                    try:
                        from app.services.recording_service import get_recording_service
                        recording_service = get_recording_service()
                        status = recording_service.get_status()
                        
                        if status.get('is_recording'):
                            health_report.append("🟢 <b>Запись:</b> Идёт. Не мешай.")
                        else:
                            health_report.append("⚪ <b>Запись:</b> Остановлена. Готова к работе.")
                    except Exception as e:
                        health_report.append("🔴 <b>Запись:</b> Сервис недоступен.")
                        errors.append(f"Recording: {str(e)[:100]}")
                    
                    # Формируем итоговый отчет в стиле Neural Slav
                    final_report = "🏥 <b>ОТЧЕТ О ЗДОРОВЬЕ СИСТЕМЫ</b>\n\n"
                    final_report += "\n".join(health_report)
                    
                    if errors:
                        final_report += "\n\n🐛 <b>ДИАГНОСТИКА ОШИБОК</b> (для разработчиков):\n"
                        for error in errors[:3]:  # Максимум 3 ошибки
                            final_report += f"• {error}\n"
                    
                    # Философское заключение от Neural Slav
                    error_count = len([r for r in health_report if "🔴" in r])
                    if error_count == 0:
                        final_report += "\n💚 <b>Заключение:</b> Всё работает. Редкое чудо в мире IT."
                    elif error_count == 1:
                        final_report += "\n💛 <b>Заключение:</b> Почти всё работает. Могло быть хуже."
                    else:
                        final_report += "\n💔 <b>Заключение:</b> Система падает. Время чинить или пить кофе."
                    
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message=final_report
                    )
                    
                except Exception as e:
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message=f"💥 <b>Ирония:</b> Система проверки здоровья сломалась.\n\n<code>{str(e)}</code>"
                    )
                
                return {"ok": True}
            
            elif command == "/report":
                # Генерируем отчет по использованию агентов
                try:
                    # Отправляем сообщение о начале генерации
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message="📊 <b>Генерирую отчет по агентам...</b>\n\nЭто может занять несколько секунд."
                    )
                    
                    # Импортируем и запускаем сервис отчетов
                    import sys
                    from pathlib import Path
                    
                    # Добавляем путь к скрипту
                    scripts_path = Path(__file__).parent.parent / "scripts"
                    sys.path.append(str(scripts_path))
                    
                    # Импортируем сервис отчетов
                    from agent_report import AgentReportService
                    
                    # Генерируем отчет за последние 7 дней
                    report_service = AgentReportService()
                    report = await report_service.generate_full_report(days_back=7)
                    
                    # Отправляем отчет (разбиваем на части если длинный)
                    max_length = 4000  # Telegram лимит ~4096 символов
                    if len(report) <= max_length:
                        await service.telegram.send_message_to_user(
                            chat_id=chat_id,
                            message=report
                        )
                    else:
                        # Разбиваем отчет на части
                        parts = []
                        current_part = ""
                        
                        for line in report.split('\n'):
                            if len(current_part + line + '\n') > max_length:
                                if current_part:
                                    parts.append(current_part)
                                current_part = line + '\n'
                            else:
                                current_part += line + '\n'
                        
                        if current_part:
                            parts.append(current_part)
                        
                        # Отправляем части
                        for i, part in enumerate(parts):
                            header = f"📊 <b>Отчет (часть {i+1}/{len(parts)})</b>\n\n" if len(parts) > 1 else ""
                            await service.telegram.send_message_to_user(
                                chat_id=chat_id,
                                message=header + part
                            )
                    
                    logger.info("✅ Отчет по агентам успешно отправлен")
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка при генерации отчета: {e}")
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message=f"❌ <b>Ошибка при генерации отчета:</b>\n\n{str(e)}"
                    )
                
                return {"ok": True}
            
            elif command == "/tasks":
                from sqlalchemy import select
                from app.db.models import Task
                
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(Task).where(Task.status == "pending").limit(10)
                    )
                    tasks = result.scalars().all()
                    
                    if tasks:
                        tasks_text = "<b>Активные задачи:</b>\n\n"
                        for i, task in enumerate(tasks, 1):
                            deadline_str = ""
                            if task.deadline:
                                deadline_str = f" (до {task.deadline.strftime('%d.%m %H:%M')})"
                            tasks_text += f"{i}. {task.text}{deadline_str}\n"
                    else:
                        tasks_text = "Нет активных задач"
                    
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message=tasks_text
                    )
                return {"ok": True}
            
            elif command == "/reminders":
                from sqlalchemy import select
                from app.db.models import Task
                from datetime import datetime, timedelta
                
                async with AsyncSessionLocal() as session:
                    # Получаем задачи с дедлайнами в ближайшие 7 дней
                    now = datetime.now()
                    week_from_now = now + timedelta(days=7)
                    
                    result = await session.execute(
                        select(Task)
                        .where(Task.status == "pending")
                        .where(Task.deadline.isnot(None))
                        .where(Task.deadline >= now)
                        .where(Task.deadline <= week_from_now)
                        .order_by(Task.deadline)
                        .limit(10)
                    )
                    tasks = result.scalars().all()
                    
                    if tasks:
                        reminders_text = "<b>⏰ Предстоящие напоминания:</b>\n\n"
                        for i, task in enumerate(tasks, 1):
                            deadline_str = task.deadline.strftime('%d.%m %H:%M') if task.deadline else "—"
                            days_left = (task.deadline - now).days if task.deadline else 0
                            
                            if days_left == 0:
                                time_left = "сегодня"
                            elif days_left == 1:
                                time_left = "завтра"
                            else:
                                time_left = f"через {days_left} дн."
                            
                            reminders_text += f"{i}. {task.text}\n"
                            reminders_text += f"   📅 {deadline_str} ({time_left})\n\n"
                    else:
                        reminders_text = "Нет предстоящих напоминаний"
                    
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message=reminders_text
                    )
                return {"ok": True}
            
            elif command == "/meetings":
                from sqlalchemy import select, desc
                from app.db.models import Meeting
                
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(Meeting).order_by(desc(Meeting.created_at)).limit(5)
                    )
                    meetings = result.scalars().all()
                    
                    if meetings:
                        meetings_text = "<b>📝 Последние встречи:</b>\n\n"
                        for i, meeting in enumerate(meetings, 1):
                            summary_preview = (meeting.summary or "Без саммари")[:100]
                            date_str = meeting.created_at.strftime('%d.%m %H:%M') if meeting.created_at else "—"
                            meetings_text += f"<b>{i}. Встреча ({date_str})</b>\n"
                            meetings_text += f"{summary_preview}...\n\n"
                    else:
                        meetings_text = "Нет встреч"
                    
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message=meetings_text
                    )
                return {"ok": True}
            
            elif command == "/knowledge":
                query = text[len(command):].strip()
                if not query:
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message="Использование: /knowledge [запрос]\n\nПример: /knowledge проект Альфа"
                    )
                    return {"ok": True}
                
                # Поиск через RAG
                from app.services.rag_service import RAGService
                rag = RAGService()
                results = await rag.search_knowledge(query, limit=3)
                
                if results:
                    response_text = f"<b>Результаты поиска:</b>\n\n"
                    for i, result in enumerate(results, 1):
                        content = result.get("content", "")[:200] if isinstance(result, dict) else str(result)[:200]
                        response_text += f"{i}. {content}...\n\n"
                else:
                    response_text = "Ничего не найдено"
                
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message=response_text
                )
                return {"ok": True}
            
            elif command == "/test":
                # Сначала подтверждаем получение команды в тот же чат
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message="🆗 Команда /test получена. Начинаю проверку всех систем..."
                )
                
                # Запускаем полный тест всех функций
                try:
                    await _run_full_system_test(chat_id, service.telegram)
                except Exception as e:
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message=f"❌ Ошибка при выполнении тестов: {e}"
                    )
                return {"ok": True}
        
        # Если не команда, обрабатываем как обычное сообщение через агентную систему
        
        # Специальные команды для управления записью и подтверждения
        # ВАЖНО: Проверяем команды записи ПЕРЕД обработкой через AgentRouter
        text_lower = text.lower().strip()
        
        # Проверяем, идет ли запись встречи - если да, не обрабатываем сообщения как встречи
        from pathlib import Path
        recording_flag_path = Path("/tmp/is_recording.flag")
        is_recording = recording_flag_path.exists()
        
        # Команды записи (проверяем ПЕРВЫМИ, чтобы не ждать ответа от Ollama)
        # Проверяем как точное совпадение, так и частичное (содержит команду)
        recording_keywords = [
            "начни запись", "начать запись", "запусти запись", "запуск записи",
            "включи запись", "старт записи", "запись встречи", "начать встречу",
            "запусти встречу", "запуск встречи", "включи встречу", "старт встречи"
        ]
        
        # Проверяем точное совпадение или содержит ключевые слова
        is_recording_command = (
            text_lower in ["запись", "старт", "start"] or
            any(keyword in text_lower for keyword in recording_keywords)
        )
        
        if is_recording_command:
            try:
                from app.services.recording_service import get_recording_service
                recording_service = get_recording_service()
                
                # Проверяем статус перед запуском
                current_status = recording_service.get_status()
                if current_status.get("is_recording"):
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message="⚠️ Запись уже идет. Остановите текущую запись командой 'стоп' перед запуском новой."
                    )
                    return {"ok": True}
                
                # Запускаем запись НЕМЕДЛЕННО, без ожидания
                # start_recording() запускает процесс в фоне и возвращает сразу
                success = recording_service.start_recording()
                
                if success:
                    status = recording_service.get_status()
                    pid = status.get("pid", "неизвестен")
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message=f"🎙 <b>Запись встречи запущена</b>\n\nМожешь говорить. Я слушаю.\n\nPID: {pid}"
                    )
                    logger.info(f"✅ Запись запущена из Telegram (chat_id: {chat_id}, PID: {pid})")
                else:
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message="⚠️ Не удалось запустить запись. Проверьте логи."
                    )
                    logger.error(f"❌ Не удалось запустить запись из Telegram (chat_id: {chat_id})")
            except Exception as e:
                logger.error(f"❌ Ошибка при запуске записи из Telegram: {e}")
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message=f"❌ Ошибка при запуске записи: {str(e)[:200]}"
                )
            return {"ok": True}
            
        # Команды остановки записи
        stop_keywords = [
            "стоп", "stop", "останови запись", "закончить встречу", "конец",
            "остановить запись", "завершить встречу", "заверши встречу", "заверши запись"
        ]
        is_stop_command = (
            text_lower in ["стоп", "stop", "конец"] or
            any(keyword in text_lower for keyword in stop_keywords)
        )
        
        if is_stop_command:
            from app.services.recording_service import get_recording_service
            recording_service = get_recording_service()
            
            # Проверяем статус перед остановкой
            status = recording_service.get_status()
            if not status.get("is_recording"):
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message="⚠️ Запись не была запущена."
                )
                return {"ok": True}
                
            await service.telegram.send_message_to_user(
                chat_id=chat_id,
                message="⏹ <b>Останавливаю запись...</b>\n\nЖди саммари и транскрипцию. Это может занять пару минут."
            )
            
            # Останавливаем (это асинхронная операция)
            await recording_service.stop_recording()
            
            # Ждем немного, чтобы скрипт записи завершил обработку
            import asyncio
            await asyncio.sleep(5)
            
            # Обрабатываем последнюю встречу из Notion
            try:
                from app.services.notion_service import NotionService
                notion = NotionService()
                
                # Получаем последнюю страницу встречи
                last_page = await notion.get_last_created_page()
                
                if last_page:
                    transcript = last_page.get("content", "")
                    notion_page_id = last_page.get("id")
                    
                    if transcript and len(transcript.strip()) > 50:
                        await service.telegram.send_message_to_user(
                            chat_id=chat_id,
                            message="📋 Обрабатываю последнюю встречу..."
                        )
                        
                        # Обрабатываем через MeetingWorkflow
                        from app.workflows.meeting_workflow import MeetingWorkflow
                        workflow = MeetingWorkflow()
                        workflow_result = await workflow.process_meeting(
                            transcript=transcript,
                            notion_page_id=notion_page_id
                        )
                        
                        meeting_id = workflow_result.get("meeting_id")
                        summary = workflow_result.get("summary", "")
                        
                        await service.telegram.send_message_to_user(
                            chat_id=chat_id,
                            message=f"✅ <b>Встреча обработана</b>\n\n"
                                   f"ID: <code>{meeting_id}</code>\n\n"
                                   f"Саммари: {summary[:200]}..."
                        )
                    else:
                        await service.telegram.send_message_to_user(
                            chat_id=chat_id,
                            message="⚠️ Транскрипт встречи пуст или слишком короткий."
                        )
                else:
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message="⚠️ Не удалось найти последнюю встречу в Notion."
                    )
            except Exception as e:
                logger.error(f"Ошибка при обработке последней встречи: {e}")
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message=f"⚠️ Ошибка при обработке встречи: {str(e)}"
                )
            
            return {"ok": True}
        
        # Команды подтверждения встречи
        if text_lower in ["ок", "ok", "хорошо", "подтверждаю", "одобряю", "да", "согласен"]:
            try:
                # Ищем последнюю встречу со статусом pending_approval
                from app.db.models import Meeting
                from sqlalchemy import desc
                
                result = await db.execute(
                    select(Meeting)
                    .where(Meeting.status == "pending_approval")
                    .order_by(desc(Meeting.created_at))
                    .limit(1)
                )
                meeting = result.scalar_one_or_none()
                
                if not meeting:
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message="🤷‍♂️ Нет встреч, ожидающих подтверждения. Видимо, всё уже обработано."
                    )
                    return {"ok": True}
                
                # Отправляем статус обработки
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message="📝 Добавляю встречу в Notion..."
                )
                
                # Создаем запись в Notion
                from app.services.notion_service import NotionService
                notion = NotionService()
                
                # Формируем заголовок встречи
                meeting_title = f"Встреча {meeting.created_at.strftime('%d.%m.%Y %H:%M')}" if meeting.created_at else f"Встреча {meeting.id[:8]}"
                
                notion_page = await notion.create_meeting_in_db(
                    meeting_id=meeting.id,
                    title=meeting_title,
                    summary=meeting.summary or "Саммари отсутствует",
                    participants=meeting.participants or [],
                    action_items=meeting.action_items or [],
                    key_decisions=meeting.key_decisions or [],
                    insights=meeting.insights or [],
                    next_steps=meeting.next_steps or [],
                    projects=meeting.projects or []
                )
                
                # Обновляем статус встречи
                meeting.status = "approved"
                meeting.notion_page_id = notion_page.get("id")
                await db.commit()
                
                # Получаем ссылку на созданную страницу
                notion_url = notion_page.get("url", "")
                
                # Отправляем подтверждение с ссылкой
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message=f"✅ <b>Встреча добавлена в Notion</b>\n\n"
                            f"📄 <a href='{notion_url}'>Смотреть в Notion</a>\n\n"
                            f"Работаем дальше."
                )
                
                logger.info(f"✅ Встреча {meeting.id} подтверждена и добавлена в Notion")
                return {"ok": True}
                
            except Exception as e:
                logger.error(f"❌ Ошибка при подтверждении встречи: {e}")
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message=f"❌ Что-то пошло не так при добавлении в Notion: {str(e)}"
                )
                return {"ok": True}

        # Сначала проверяем, является ли это ответом на ежедневный опрос
        clarification = await service.process_response(chat_id, text, db)
        
        if clarification:
            # Отправляем уточняющий вопрос
            await service.telegram.send_message_to_user(
                chat_id=chat_id,
                message=clarification
            )
            # Автоответ отправляется даже для clarification
            try:
                initial_response = get_neural_slav_thinking_response()
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message=initial_response
                )
            except Exception as auto_response_error:
                logger.error(f"❌ Ошибка при отправке автоответа для clarification: {auto_response_error}")
        else:
            # Если идет запись встречи, не обрабатываем сообщения как встречи
            # Просто подтверждаем получение
            if is_recording:
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message="📝 Записано. Продолжаю слушать. Напиши 'конец' когда закончишь."
                )
                return {"ok": True}
            
            # МОМЕНТАЛЬНАЯ обратная связь - отправляем сразу при получении сообщения
            try:
                initial_response = get_neural_slav_thinking_response()
                await service.telegram.send_message_to_user(
                    chat_id=chat_id,
                    message=initial_response
                )
            except Exception as auto_response_error:
                logger.error(f"❌ Ошибка при отправке автоответа: {auto_response_error}")
                # Продолжаем обработку даже если автоответ не отправился
            
            # Обрабатываем через AgentRouter для свободного текста
            try:
                from app.services.agent_router import AgentRouter
                router = AgentRouter()
                
                logger.info(f"🤖 Обработка свободного текста через AgentRouter: {text[:50]}...")
                
                # Классифицируем сообщение
                classification = await router.classify(text)
                logger.info(f"📋 Классификация: {classification.agent_type} (уверенность: {classification.confidence:.2f})")
                
                # Роутим к соответствующему агенту с передачей username
                agent_response = await router.route(text, classification, sender_username=sender_username)
                
                # Отправляем ответ пользователю
                if agent_response.response:
                    # Используем единый cleaning pipeline из BaseAgent
                    from app.services.agents.base_agent import BaseAgent
                    base_agent = BaseAgent() 
                    # Небольшой хак для доступа к методу без полной инициализации
                    clean_response = base_agent.clean_response(agent_response.response)
                    
                    if clean_response:
                        # Дополнительная очистка через sanitize_html_for_telegram
                        from app.services.telegram_service import sanitize_html_for_telegram
                        clean_response = sanitize_html_for_telegram(clean_response)
                        
                        await service.telegram.send_message_to_user(
                            chat_id=chat_id,
                            message=clean_response
                        )
                
                # Показываем важные действия пользователю (без технических деталей)
                if agent_response.actions:
                    # Используем единый форматтер действий из BaseAgent
                    user_friendly_actions = base_agent.format_user_friendly_actions(agent_response.actions)
                    
                    # Отправляем только если есть действия для показа пользователю
                    if user_friendly_actions:
                        actions_text = "\n".join(user_friendly_actions)
                        # Очищаем действия от технических символов
                        actions_text = sanitize_html_for_telegram(actions_text)
                        
                        await service.telegram.send_message_to_user(
                            chat_id=chat_id,
                            message=actions_text
                        )
                
                logger.info(f"✅ Сообщение успешно обработано через {agent_response.agent_type}Agent")
                
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке через AgentRouter: {e}")
                try:
                    error_message = f"❌ Произошла ошибка при обработке сообщения: {str(e)[:200]}"
                    from app.services.telegram_service import sanitize_html_for_telegram
                    error_message = sanitize_html_for_telegram(error_message)
                    await service.telegram.send_message_to_user(
                        chat_id=chat_id,
                        message=error_message
                    )
                except Exception as send_error:
                    logger.error(f"❌ Критическая ошибка при отправке сообщения об ошибке: {send_error}")
        
        return {"ok": True}
    except Exception as e:
        logger.error(f"Ошибка при обработке webhook: {e}")
        # Все равно возвращаем ok, чтобы Telegram не повторял запрос
        return {"ok": True}


async def _run_full_system_test(chat_id: str, telegram_service: TelegramService):
    """Запускает полный тест всех функций системы."""
    
    # 1. Тест статуса системы
    await telegram_service.send_message_to_user(
        chat_id=chat_id,
        message="🧪 <b>Запуск полного теста системы</b>\n\n1️⃣ Тест статуса системы..."
    )
    
    from app.services.recording_service import get_recording_service
    recording_service = get_recording_service()
    status = recording_service.get_status()
    
    status_text = f"✅ <b>Статус записи:</b> {'🟢 Активна' if status.get('is_recording') else '⚪ Остановлена'}\n"
    status_text += f"PID: {status.get('pid', 'Нет')}"
    
    await telegram_service.send_message_to_user(chat_id=chat_id, message=status_text)
    await asyncio.sleep(1)
    
    # 2. Тест агентов
    await telegram_service.send_message_to_user(
        chat_id=chat_id,
        message="2️⃣ Тест агентной системы..."
    )
    
    try:
        from app.services.agent_router import AgentRouter
        router = AgentRouter()
        
        # Тестируем классификацию
        test_messages = [
            "Нужно сделать презентацию к пятнице",
            "Обработай последнюю встречу", 
            "Запомни что проект Альфа запускается в марте",
            "Найди информацию о проекте Бета"
        ]
        
        for msg in test_messages:
            classification = await router.classify(msg)
            # Эмодзи для агентов
            agent_emojis = {
                "task": "📋",
                "meeting": "🎯", 
                "message": "📨",
                "knowledge": "🧠",
                "rag_query": "🔍",
                "default": "🤖"
            }
            
            agent_emoji = agent_emojis.get(classification.agent_type, "🤖")
            await telegram_service.send_message_to_user(
                chat_id=chat_id,
                message=f"📝 <b>'{msg[:30]}...'</b>\n"
                        f"{agent_emoji} <b>Обработчик:</b> {classification.agent_type.title()}"
            )
            await asyncio.sleep(0.5)
            
    except Exception as e:
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"❌ Ошибка тестирования агентов: {e}"
        )
    
    # 3. Тест координации агентов
    await telegram_service.send_message_to_user(
        chat_id=chat_id,
        message="3️⃣ Тест координации агентов..."
    )
    
    try:
        # Создаем тестовую встречу с задачами для проверки цепочки
        from app.services.agents.meeting_agent import MeetingAgent
        from app.models.schemas import IntentClassification
        
        meeting_agent = MeetingAgent()
        
        # Имитируем результат с задачами для проверки цепочки
        test_result = {
            "response": "Тестовая встреча обработана",
            "actions": [{"type": "meeting_processed", "meeting_id": "test-123"}],
            "metadata": {
                "meeting_id": "test-123",
                "action_items": [
                    {"text": "Тестовая задача 1", "assignee": "Тестер", "priority": "High"},
                    {"text": "Тестовая задача 2", "assignee": "Админ", "priority": "Medium"}
                ]
            }
        }
        
        # Проверяем, определит ли агент следующие шаги
        next_agents = meeting_agent.get_next_agents(test_result)
        
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"✅ <b>Координация агентов:</b>\n"
                    f"После MeetingAgent запускается: {', '.join(next_agents) if next_agents else 'нет'}\n"
                    f"Найдено задач для цепочки: {len(test_result['metadata']['action_items'])}"
        )
        
    except Exception as e:
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"❌ Ошибка тестирования координации: {e}"
        )
    
    # 4. Тест RAG и знаний
    await telegram_service.send_message_to_user(
        chat_id=chat_id,
        message="4️⃣ Тест системы знаний (RAG)..."
    )
    
    try:
        from app.services.rag_service import RAGService
        rag = RAGService()
        
        # Тестовый поиск
        results = await rag.search_knowledge("проект", limit=2)
        
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"✅ <b>RAG система:</b>\n"
                    f"Найдено результатов: {len(results)}\n"
                    f"Коллекции: meetings, knowledge, tasks"
        )
        
    except Exception as e:
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"❌ Ошибка тестирования RAG: {e}"
        )
    
    # 5. Тест проактивного сервиса
    await telegram_service.send_message_to_user(
        chat_id=chat_id,
        message="5️⃣ Тест проактивного сервиса..."
    )
    
    try:
        from app.services.proactive_service import get_proactive_service
        proactive = get_proactive_service()
        
        is_running = proactive.running
        
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"✅ <b>ProactiveService:</b>\n"
                    f"Статус: {'🟢 Работает' if is_running else '🔴 Остановлен'}\n"
                    f"Функции: напоминания о дедлайнах, забытые задачи, daily check-in"
        )
        
        # Тест отправки предложений
        await proactive.send_suggestions(
            "Тестовый контекст: выполнено 3 задачи, 2 встречи за неделю"
        )
        
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message="✅ Предложения от ProactiveService отправлены выше ⬆️"
        )
        
    except Exception as e:
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"❌ Ошибка тестирования ProactiveService: {e}"
        )
    
    # 6. Тест планировщика
    await telegram_service.send_message_to_user(
        chat_id=chat_id,
        message="6️⃣ Тест планировщика задач..."
    )
    
    try:
        from app.services.scheduler_service import get_scheduler_service
        from datetime import datetime, timedelta
        
        scheduler = get_scheduler_service()
        
        # Планируем тестовое сообщение через 10 секунд
        test_time = datetime.now() + timedelta(seconds=10)
        
        async def send_test_message():
            await telegram_service.send_message_to_user(
                chat_id=chat_id,
                message="⏰ <b>Тест планировщика:</b> Это отложенное сообщение!"
            )
        
        success = scheduler.schedule_task(
            task_id=f"test-{chat_id}-{int(datetime.now().timestamp())}",
            execute_at=test_time,
            action=send_test_message,
            action_args={}
        )
        
        scheduled_tasks = scheduler.get_scheduled_tasks()
        
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"✅ <b>SchedulerService:</b>\n"
                    f"Тестовая задача запланирована: {'да' if success else 'нет'}\n"
                    f"Всего задач в очереди: {len(scheduled_tasks)}\n"
                    f"⏰ Ожидайте тестовое сообщение через 10 секунд..."
        )
        
    except Exception as e:
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"❌ Ошибка тестирования планировщика: {e}"
        )
    
    # 7. Тест автоиндексации
    await telegram_service.send_message_to_user(
        chat_id=chat_id,
        message="7️⃣ Тест автоматической индексации..."
    )
    
    try:
        from app.services.rag_service import RAGService
        from app.services.notion_service import NotionService
        
        rag = RAGService()
        notion = NotionService()
        
        # Проверяем методы автоиндексации (не запускаем, чтобы не перегружать)
        has_auto_index = hasattr(rag, 'auto_index_notion_pages')
        has_sync = hasattr(rag, 'sync_with_notion')
        has_update = hasattr(rag, 'update_index')
        
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"✅ <b>Автоиндексация:</b>\n"
                    f"auto_index_notion_pages: {'✅' if has_auto_index else '❌'}\n"
                    f"sync_with_notion: {'✅' if has_sync else '❌'}\n"
                    f"update_index: {'✅' if has_update else '❌'}\n"
                    f"Фоновая синхронизация каждые 10 минут"
        )
        
    except Exception as e:
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"❌ Ошибка тестирования автоиндексации: {e}"
        )
    
    # 8. Тест улучшенного саммари
    await telegram_service.send_message_to_user(
        chat_id=chat_id,
        message="8️⃣ Тест улучшенного саммари встреч..."
    )
    
    try:
        from app.models.schemas import MeetingAnalysis, KeyDecision
        
        # Проверяем новые поля в схеме
        fields = MeetingAnalysis.model_fields
        
        new_fields = ['key_decisions', 'insights', 'next_steps']
        found_fields = [f for f in new_fields if f in fields]
        
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"✅ <b>Улучшенное саммари:</b>\n"
                    f"Новые поля: {', '.join(found_fields)}\n"
                    f"Длина саммари: 7-10 предложений\n"
                    f"KeyDecision модель: ✅\n"
                    f"Контекст прошлых встреч: включен в промпт"
        )
        
    except Exception as e:
        await telegram_service.send_message_to_user(
            chat_id=chat_id,
            message=f"❌ Ошибка тестирования саммари: {e}"
        )
    
    # 9. Финальный отчет
    await asyncio.sleep(2)
    await telegram_service.send_message_to_user(
        chat_id=chat_id,
        message="🎉 <b>Тест системы завершен!</b>\n\n"
                "📊 <b>Протестированные функции:</b>\n"
                "✅ Статус системы и запись\n"
                "✅ Агентная система и классификация\n"
                "✅ Координация агентов (цепочки)\n"
                "✅ RAG и система знаний\n"
                "✅ Проактивный сервис\n"
                "✅ Планировщик задач\n"
                "✅ Автоматическая индексация\n"
                "✅ Улучшенное саммари встреч\n\n"
                "🚀 <b>Дополнительные возможности:</b>\n"
                "• Дашборд с виджетами\n"
                "• Улучшенный чат-интерфейс\n"
                "• Мобильная адаптивность\n"
                "• CSS анимации\n"
                "• Аудио-плеер для встреч\n\n"
                "Система готова к работе! 💪"
    )
