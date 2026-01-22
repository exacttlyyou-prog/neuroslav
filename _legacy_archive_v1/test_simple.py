"""
Простой тест для проверки работы с конкретными страницами.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from services.notion_service import NotionService
from loguru import logger

# Настройка логирования
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

# ID страниц из ссылок
PAGE_IDS = [
    "2edfa7fd637180b98715fa9f348f90f9",  # https://www.notion.so/2026-2edfa7fd637180b98715fa9f348f90f9
    "ce32758331a5406694f86b8bd292605a",  # https://www.notion.so/AI-Context-ce32758331a5406694f86b8bd292605a
]

async def main():
    print("🚀 Тест получения контента из Notion страниц...\n")
    
    notion = NotionService()
    
    for page_id in PAGE_IDS:
        print(f"{'='*60}")
        print(f"📄 Страница: {page_id}")
        print(f"{'='*60}\n")
        
        try:
            page_id_result, title, content = await notion.get_latest_meeting_notes(page_id)
            
            if content and len(content.strip()) >= 50:
                print(f"✅ Успешно получен контент!")
                print(f"   Заголовок: {title}")
                print(f"   Длина: {len(content)} символов")
                print(f"\n   Первые 300 символов:\n   {content[:300]}...\n")
            else:
                print(f"❌ Контент не получен или слишком короткий")
                print(f"   Длина: {len(content) if content else 0} символов\n")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}\n")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
