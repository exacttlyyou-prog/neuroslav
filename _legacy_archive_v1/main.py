"""
Локальный Telegram бот для анализа встреч и обработки сообщений.
Использует Ollama (локальный AI) и ChromaDB (RAG).
"""
import asyncio
import sys
from pathlib import Path
from uuid import uuid4
from typing import Dict, Any

# Добавляем корневую директорию в путь
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from loguru import logger

from core.config import get_settings
from core.ai_service import OllamaClient
from core.rag_service import LocalRAG
from core.contacts_service import ContactsService
from core.context_loader import ContextLoader
from services.notion_service import NotionService
from core.schemas import MeetingAnalysis, MessageClassification

# Загружаем переменные окружения
load_dotenv()

# Глобальное состояние (в памяти)
pending_approvals: Dict[str, Dict[str, Any]] = {}

# Глобальные переменные для сервисов (инициализируются в main())
settings: Any = None
context_loader: Any = None
rag_service: Any = None
contacts_service: Any = None
notion_service: Any = None
ai_service: Any = None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start с системой авторизации."""
    user = update.effective_user
    if not user:
        await update.message.reply_text("❌ Ошибка: не удалось определить пользователя")
        return
    
    try:
        # Формируем данные пользователя Telegram
        tg_user_data = {
            'id': user.id,
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'username': user.username or ''
        }
        
        # Получаем или создаем пользователя в Notion
        user_data = await notion_service.get_or_create_user(tg_user_data)
        status = user_data.get('status', 'Unknown')
        is_new = user_data.get('is_new', False)
        name = user_data.get('name', user.first_name or 'Пользователь')
        
        # Уведомление админу при создании нового пользователя
        if is_new:
            admin_chat_id = settings.admin_chat_id
            if admin_chat_id:
                try:
                    from telegram import Bot
                    admin_bot = Bot(token=settings.telegram_bot_token)
                    username_display = f"@{user.username}" if user.username else "без username"
                    admin_message = (
                        f"⚠️ <b>Новый пользователь:</b>\n"
                        f"👤 {name}\n"
                        f"📱 {username_display}\n"
                        f"🆔 ChatID: <code>{user.id}</code>\n\n"
                        f"Добавлен в Notion со статусом <b>Pending</b>."
                    )
                    await admin_bot.send_message(
                        chat_id=admin_chat_id,
                        text=admin_message,
                        parse_mode='HTML'
                    )
                    logger.info(f"Админ уведомлен о новом пользователе: {name}")
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления админу: {e}")
        
        # Обработка разных статусов
        if status == "Active":
            await update.message.reply_text(
                f"Привет, {name}! Нейрослав на связи. Жди саммари.",
                parse_mode='HTML'
            )
        elif status == "Pending":
            await update.message.reply_text(
                "Заявка принята. Ожидай подтверждения от администратора."
            )
        elif status == "Blocked":
            await update.message.reply_text("Доступ запрещен.")
        else:
            await update.message.reply_text(
                f"Статус: {status}. Ожидай подтверждения от администратора."
            )
            
    except Exception as e:
        logger.error(f"Ошибка при обработке /start: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def process_meeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /analyze - анализ встречи из Notion."""
    await update.message.reply_text("🔍 Анализирую последнюю встречу из Notion...")
    
    try:
        # 1. Читаем последнюю встречу из Notion
        page_id = settings.notion_meeting_page_id
        logger.info(f"Чтение последней встречи из страницы: {page_id}")
        block_id, title, meeting_content = await notion_service.get_latest_meeting_notes(page_id)
        
        if not meeting_content or len(meeting_content.strip()) < 50:
            await update.message.reply_text("❌ Не удалось найти встречу или контент слишком короткий")
            return
        
        # 2. RAG: ищем похожие прошлые встречи
        logger.info("Поиск похожих встреч в ChromaDB...")
        similar_meetings = rag_service.search_similar(meeting_content, n_results=3)
        
        context_texts = []
        for meeting in similar_meetings:
            context_texts.append(f"Саммари: {meeting.get('summary', '')}\nЗадачи: {meeting.get('action_items', '')}")
        
        # 3. Анализируем через Ollama
        logger.info("Анализ через Ollama...")
        sender_username = update.effective_user.username if update.effective_user else None
        analysis = await ai_service.analyze_meeting(
            content=meeting_content,
            context=context_texts,
            response_schema=MeetingAnalysis,
            sender_username=sender_username
        )
        
        # 4. Формируем сообщение для Telegram (HTML)
        from services.telegram_service import sanitize_html_for_telegram
        summary_clean = sanitize_html_for_telegram(analysis.summary_md)
        message_text = f"📋 <b>Саммари встречи</b>\n\n{summary_clean}\n\n"
        
        if analysis.action_items:
            message_text += "<b>Задачи:</b>\n"
            for i, item in enumerate(analysis.action_items[:10], 1):
                priority_emoji = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}.get(item.priority, '⚪')
                assignee_text = f" ({item.assignee})" if item.assignee else ""
                message_text += f"{i}. {priority_emoji} {item.text}{assignee_text}\n"
            if len(analysis.action_items) > 10:
                message_text += f"\n... и еще {len(analysis.action_items) - 10} задач\n"
        
        if analysis.risk_assessment:
            message_text += f"\n⚠️ <b>RISKS:</b> {analysis.risk_assessment}\n"
        
        # 5. Создаем кнопки
        session_id = str(uuid4())
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve & Save", callback_data=f"approve_{session_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{session_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 6. Отправляем сообщение
        sent_message = await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # 7. Сохраняем черновик в памяти
        pending_approvals[session_id] = {
            'meeting_content': meeting_content,
            'analysis': analysis,
            'message_id': sent_message.message_id,
            'chat_id': update.effective_chat.id
        }
        
        logger.info(f"Создана сессия анализа: {session_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при анализе встречи: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик входящих текстовых сообщений."""
    message = update.message
    
    # Определяем автора (оригинального, если это Forward)
    if message.forward_from:
        author_user = message.forward_from
        message_text = message.text or message.caption or ""
    else:
        author_user = message.from_user
        message_text = message.text or ""
    
    if not message_text:
        await message.reply_text("❌ Не могу обработать сообщение без текста")
        return
    
    try:
        # 1. Разрешаем автора через ContactsService
        author_info = contacts_service.resolve_user(author_user)
        logger.info(f"Сообщение от {author_info['name']} ({author_info['role']})")
        
        # 2. Классифицируем через Ollama
        await message.reply_text("🤖 Анализирую сообщение...")
        author_username = author_user.username if author_user else None
        classification = await ai_service.classify_message(
            text=message_text,
            author_name=author_info['name'],
            author_role=author_info['role'],
            author_username=author_username
        )
        
        # Валидируем через Pydantic
        msg_class = MessageClassification(**classification)
        
        # 3. Action Router
        if msg_class.type == "knowledge":
            # Сохраняем в ChromaDB
            rag_service.save_knowledge(
                text=message_text,
                summary=msg_class.summary
            )
            await message.reply_text("🧠 Запомнил")
            
        elif msg_class.type == "task":
            # Создаем задачу в Notion
            from core.schemas import ActionItem
            action_item = ActionItem(
                text=msg_class.summary,
                assignee=author_info['name'],
                priority='Medium'
            )
            page_id = settings.notion_meeting_page_id
            await notion_service.create_tasks(page_id, [action_item])
            await message.reply_text("✅ Задача создана")
            
        elif msg_class.type == "reminder":
            # Заглушка для напоминаний
            datetime_text = f" {msg_class.datetime}" if msg_class.datetime else ""
            await message.reply_text(
                f"⏰ Я увидел время{datetime_text}, но модуль напоминаний еще в разработке. "
                "Просто напомню текстом сейчас."
            )
        else:
            await message.reply_text(f"❓ Неизвестный тип сообщения: {msg_class.type}")
            
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        await message.reply_text(f"❌ Ошибка: {e}")


async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик Reply сообщений (для обновления черновиков саммари)."""
    message = update.message
    reply_to = message.reply_to_message
    
    if not reply_to or not reply_to.text:
        return
    
    # Ищем сессию по message_id
    session_id = None
    for sid, data in pending_approvals.items():
        if data.get('message_id') == reply_to.message_id:
            session_id = sid
            break
    
    if not session_id:
        return
    
    try:
        # Обновляем черновик
        new_text = message.text
        # Здесь можно добавить логику обновления анализа через Ollama
        # Пока просто обновляем саммари в черновике
        pending_approvals[session_id]['analysis'].summary_md = new_text
        
        # Отправляем обновленную версию
        analysis = pending_approvals[session_id]['analysis']
        from services.telegram_service import sanitize_html_for_telegram
        summary_clean = sanitize_html_for_telegram(analysis.summary_md)
        message_text = f"📋 <b>Обновленное саммари</b>\n\n{summary_clean}\n\n"
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve & Save", callback_data=f"approve_{session_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{session_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении черновика: {e}")
        await message.reply_text(f"❌ Ошибка при обновлении: {e}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback queries (кнопки Approve/Cancel)."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("approve_"):
        session_id = data.replace("approve_", "")
        await approve_analysis(query, session_id)
    elif data.startswith("cancel_"):
        session_id = data.replace("cancel_", "")
        await cancel_analysis(query, session_id)


async def approve_analysis(query, session_id: str):
    """Одобрение анализа и создание задач в Notion."""
    if session_id not in pending_approvals:
        await query.edit_message_text("❌ Сессия не найдена")
        return
    
    try:
        session_data = pending_approvals[session_id]
        analysis = session_data['analysis']
        meeting_content = session_data['meeting_content']
        
        # 1. Создаем задачи в Notion
        page_id = settings.notion_meeting_page_id
        await notion_service.create_tasks(page_id, analysis.action_items)
        
        # 2. Сохраняем в ChromaDB
        rag_service.save_approved(
            meeting_text=meeting_content,
            summary=analysis.summary_md,
            action_items=analysis.action_items
        )
        
        # 3. Удаляем из pending_approvals
        del pending_approvals[session_id]
        
        await query.edit_message_text(
            "✅ База знаний обновлена, задачи поставлены",
            reply_markup=None
        )
        
        logger.info(f"Анализ одобрен и сохранен: {session_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при одобрении анализа: {e}")
        await query.edit_message_text(f"❌ Ошибка: {e}")


async def cancel_analysis(query, session_id: str):
    """Отмена анализа."""
    if session_id in pending_approvals:
        del pending_approvals[session_id]
    
    await query.edit_message_text("❌ Анализ отменен", reply_markup=None)


async def reload_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /refresh - перезагрузка контекста из Notion."""
    await update.message.reply_text("🔄 Обновляю контекст из Notion...")
    try:
        # Используем asyncio для вызова async метода
        import asyncio
        await context_loader.sync_context_from_notion()
        await update.message.reply_text(
            f"✅ Контекст обновлен!\n"
            f"Людей: {len(context_loader.people)}\n"
            f"Проектов: {len(context_loader.projects)}"
        )
    except Exception as e:
        logger.error(f"Ошибка при обновлении контекста: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def initialize_services():
    """Инициализация всех сервисов (async)."""
    global settings, context_loader, rag_service, contacts_service, notion_service, ai_service
    
    settings = get_settings()
    context_loader = ContextLoader()
    rag_service = LocalRAG()
    contacts_service = ContactsService()
    notion_service = NotionService()
    ai_service = OllamaClient(context_loader=context_loader)
    
    # Загружаем контекст из Notion (async)
    try:
        await context_loader.sync_context_from_notion()
        logger.info(f"Загружено контекста из Notion: {len(context_loader.people)} людей, {len(context_loader.projects)} проектов")
    except Exception as e:
        logger.warning(f"Не удалось загрузить контекст из Notion: {e}, используем JSON fallback")
        logger.info(f"Загружено контекста из JSON: {len(context_loader.people)} людей, {len(context_loader.projects)} проектов")


async def post_init(application):
    """Callback для инициализации сервисов после создания приложения."""
    await initialize_services()


def main():
    """Главная функция запуска бота."""
    logger.info("Запуск локального Telegram бота...")
    
    # Создаем приложение с post_init callback
    application = (
        ApplicationBuilder()
        .token(get_settings().telegram_bot_token)
        .post_init(post_init)
        .build()
    )
    
    # Регистрируем handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("analyze", process_meeting))
    application.add_handler(CommandHandler("refresh", reload_context))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.REPLY, handle_reply))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.FORWARDED, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Запускаем polling
    logger.info("Бот запущен в режиме polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

