"""
Автоматический мониторинг Notion страницы с анализом новых встреч.
Polling loop для непрерывного отслеживания изменений.
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from dotenv import load_dotenv
from telegram import Bot
from loguru import logger

from core.config import get_settings
from core.ai_service import OllamaClient
from core.context_loader import ContextLoader
from core.rag_service import LocalRAG
from core.schemas import MeetingAnalysis
from services.notion_service import NotionService

# Загружаем переменные окружения
load_dotenv()

# Глобальное состояние
last_processed_block_id: str | None = None


async def process_new_entry(
    block_id: str,
    title: str,
    content: str,
    notion_service: NotionService,
    ai_service: OllamaClient,
    rag_service: LocalRAG,
    telegram_bot: Bot,
    admin_chat_id: str
) -> None:
    """
    Обрабатывает новую запись: анализирует через AI и отправляет в Telegram.
    
    Args:
        block_id: ID блока Notion
        title: Заголовок записи
        content: Содержимое записи
        notion_service: Сервис для работы с Notion
        ai_service: Сервис для AI анализа
        rag_service: Сервис для RAG поиска
        telegram_bot: Telegram бот
        admin_chat_id: ID чата для отправки
    """
    try:
        print(f"🚀 New entry detected! Processing '{title}'...")
        
        # 1. Ищем похожие встречи в RAG
        similar_meetings = rag_service.search_similar(content, n_results=3)
        context_texts = []
        for meeting in similar_meetings:
            context_texts.append(f"Саммари: {meeting.get('summary', '')}\nЗадачи: {meeting.get('action_items', '')}")
        
        # 2. Анализируем через AI
        print(f"🧠 Analyzing with AI (Sudo Slava)...")
        analysis = await ai_service.analyze_meeting(
            content=content,
            context=context_texts,
            response_schema=MeetingAnalysis,
            sender_username=None
        )
        
        print("✅ Analysis complete")
        
        # 3. Формируем сообщение для Telegram (HTML)
        from services.telegram_service import sanitize_html_for_telegram
        summary_clean = sanitize_html_for_telegram(analysis.summary_md)
        message_text = f"📋 <b>Саммари встречи: {title}</b>\n\n{summary_clean}\n\n"
        
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
        
        # 4. Отправляем в Telegram
        print("📤 Sending to Telegram...")
        await telegram_bot.send_message(
            chat_id=admin_chat_id,
            text=message_text,
            parse_mode='HTML'
        )
        
        print("✅ Sent to Telegram!")
        
    except Exception as e:
        logger.error(f"Ошибка при обработке новой записи: {e}")
        print(f"❌ Ошибка при обработке: {e}")


async def check_for_new_entry(
    notion_service: NotionService,
    ai_service: OllamaClient,
    rag_service: LocalRAG,
    telegram_bot: Bot,
    page_id: str,
    admin_chat_id: str
) -> None:
    """
    Проверяет наличие новой записи на странице Notion.
    
    Args:
        notion_service: Сервис для работы с Notion
        ai_service: Сервис для AI анализа
        rag_service: Сервис для RAG поиска
        telegram_bot: Telegram бот
        page_id: ID страницы Notion
        admin_chat_id: ID чата для отправки
    """
    global last_processed_block_id
    
    try:
        # Получаем последнюю запись
        block_id, title, content = await notion_service.get_latest_meeting_notes(page_id)
        
        if not block_id:
            logger.warning("Не удалось получить ID блока")
            return
        
        if not content or len(content.strip()) < 50:
            logger.debug("Контент слишком короткий или пустой")
            return
        
        # Проверяем, изменился ли ID
        if block_id != last_processed_block_id:
            # Новая запись обнаружена
            await process_new_entry(
                block_id=block_id,
                title=title,
                content=content,
                notion_service=notion_service,
                ai_service=ai_service,
                rag_service=rag_service,
                telegram_bot=telegram_bot,
                admin_chat_id=admin_chat_id
            )
            
            # Обновляем ID последнего обработанного блока
            last_processed_block_id = block_id
            logger.info(f"Обновлен last_processed_block_id: {block_id}")
        else:
            logger.debug("Новых записей не обнаружено")
            
    except Exception as e:
        logger.error(f"Ошибка при проверке новой записи: {e}")
        print(f"⚠️ Ошибка при проверке: {e} (продолжаю мониторинг...)")


async def initialize_watcher(
    notion_service: NotionService,
    page_id: str
) -> None:
    """
    Инициализирует watcher: читает последнюю запись и сохраняет её ID.
    
    Args:
        notion_service: Сервис для работы с Notion
        page_id: ID страницы Notion
    """
    global last_processed_block_id
    
    try:
        print("🔍 Initializing watcher...")
        block_id, title, content = await notion_service.get_latest_meeting_notes(page_id)
        
        if block_id:
            last_processed_block_id = block_id
            print(f"✅ Watcher initialized. Last entry: '{title}' (ID: {block_id})")
            print("👀 Monitoring page for new entries...")
        else:
            print("⚠️ Не удалось получить последнюю запись при инициализации")
            last_processed_block_id = None
            
    except Exception as e:
        logger.error(f"Ошибка при инициализации watcher: {e}")
        print(f"❌ Ошибка при инициализации: {e}")
        last_processed_block_id = None


async def main():
    """Главная функция watcher'а."""
    global last_processed_block_id
    
    print("🚀 Starting Notion Watcher...")
    
    try:
        # Инициализация сервисов
        settings = get_settings()
        print("✅ Settings loaded")
        
        # Проверяем наличие необходимых переменных
        if not settings.notion_meeting_page_id:
            print("❌ Ошибка: NOTION_MEETING_PAGE_ID не установлен в .env")
            return
        
        if not settings.telegram_bot_token:
            print("❌ Ошибка: TELEGRAM_BOT_TOKEN не установлен в .env")
            return
        
        if not settings.admin_chat_id:
            print("❌ Ошибка: ADMIN_CHAT_ID не установлен в .env")
            return
        
        # Инициализируем сервисы
        print("🔧 Initializing services...")
        context_loader = ContextLoader()
        rag_service = LocalRAG()
        notion_service = NotionService()
        ai_service = OllamaClient(context_loader=context_loader)
        telegram_bot = Bot(token=settings.telegram_bot_token)
        
        # Загружаем контекст из Notion (async)
        try:
            await context_loader.sync_context_from_notion()
            print(f"✅ Загружено контекста из Notion: {len(context_loader.people)} людей, {len(context_loader.projects)} проектов")
        except Exception as e:
            logger.warning(f"Не удалось загрузить контекст из Notion: {e}, используем JSON fallback")
            print(f"✅ Загружено контекста из JSON: {len(context_loader.people)} людей, {len(context_loader.projects)} проектов")
        
        print("✅ Services initialized")
        
        # Инициализируем watcher (читаем последнюю запись, но не отправляем)
        page_id = settings.notion_meeting_page_id
        await initialize_watcher(notion_service, page_id)
        
        # Основной цикл мониторинга
        print("\n🔄 Starting polling loop (60 seconds interval)...")
        print("Press Ctrl+C to stop\n")
        
        while True:
            try:
                await check_for_new_entry(
                    notion_service=notion_service,
                    ai_service=ai_service,
                    rag_service=rag_service,
                    telegram_bot=telegram_bot,
                    page_id=page_id,
                    admin_chat_id=settings.admin_chat_id
                )
            except KeyboardInterrupt:
                print("\n\n⏹️ Watcher stopped by user")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                print(f"⚠️ Ошибка в цикле: {e} (продолжаю...)")
            
            # Ждем 60 секунд перед следующей проверкой
            await asyncio.sleep(60)
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Watcher stopped by user")
    except Exception as e:
        logger.error(f"Критическая ошибка watcher'а: {e}")
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"❌ Fatal error: {e}")

