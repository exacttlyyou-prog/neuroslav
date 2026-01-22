"""
Скрипт для проверки доступности Notion баз данных и отправки отчета Славе.
"""
import asyncio
import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.telegram_service import TelegramService
from app.services.notion_service import NotionService
from app.config import get_settings
from loguru import logger


async def check_notion_and_send():
    """Проверяет доступность Notion и отправляет отчет."""
    try:
        telegram = TelegramService()
        settings = get_settings()
        
        # Проверяем Telegram токен
        is_valid = await telegram.validate_token()
        if not is_valid:
            logger.error("❌ Telegram токен невалиден")
            return
        
        report_lines = ["📋 <b>Проверка Notion API</b>\n"]
        
        # Проверяем Notion токен
        try:
            notion = NotionService()
            notion_valid = await notion.validate_token()
            
            if notion_valid:
                report_lines.append("✅ Notion токен валиден\n")
                
                # Проверяем People DB
                if settings.notion_people_db_id:
                    try:
                        contacts = await notion.get_contacts_from_db()
                        report_lines.append(f"✅ Люди: {len(contacts)} контактов")
                        if contacts:
                            names = [c.get('name', 'N/A') for c in contacts[:5]]
                            report_lines.append(f"   Примеры: {', '.join(names)}")
                    except Exception as e:
                        report_lines.append(f"❌ Люди: ошибка - {str(e)[:50]}")
                else:
                    report_lines.append("⚠️ Люди: NOTION_PEOPLE_DB_ID не установлен")
                
                # Проверяем Projects DB
                if settings.notion_projects_db_id:
                    try:
                        projects = await notion.get_projects_from_db()
                        report_lines.append(f"✅ Проекты: {len(projects)} проектов")
                    except Exception as e:
                        report_lines.append(f"❌ Проекты: ошибка - {str(e)[:50]}")
                else:
                    report_lines.append("⚠️ Проекты: NOTION_PROJECTS_DB_ID не установлен")
                
                # Проверяем Glossary DB
                if settings.notion_glossary_db_id:
                    try:
                        glossary = await notion.get_glossary_from_db()
                        report_lines.append(f"✅ Глоссарий: {len(glossary)} терминов")
                    except Exception as e:
                        report_lines.append(f"❌ Глоссарий: ошибка - {str(e)[:50]}")
                else:
                    report_lines.append("⚠️ Глоссарий: NOTION_GLOSSARY_DB_ID не установлен")
                
                # Проверяем Meeting Page
                if settings.notion_meeting_page_id:
                    try:
                        page = await notion.client.pages.retrieve(settings.notion_meeting_page_id)
                        report_lines.append(f"✅ Страница встреч: доступна")
                    except Exception as e:
                        report_lines.append(f"❌ Страница встреч: ошибка - {str(e)[:50]}")
                else:
                    report_lines.append("⚠️ Страница встреч: NOTION_MEETING_PAGE_ID не установлен")
                
            else:
                report_lines.append("❌ Notion токен невалиден")
                
        except Exception as e:
            report_lines.append(f"❌ Ошибка при проверке Notion: {str(e)[:100]}")
        
        # Отправляем отчет
        message = "\n".join(report_lines)
        message_id = await telegram.send_notification(message)
        logger.info(f"✅ Отчет отправлен! Message ID: {message_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_notion_and_send())
