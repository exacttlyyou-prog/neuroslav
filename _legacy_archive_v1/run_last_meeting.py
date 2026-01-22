import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в пути поиска модулей
sys.path.insert(0, str(Path(__file__).parent))

from services.notion_service import NotionService

async def main():
    print("🚀 Запуск теста...")
    notion = NotionService()
    
    # Получаем настройки для ID страницы
    from core.config import get_settings
    settings = get_settings()
    page_id = settings.notion_meeting_page_id
    
    if not page_id:
        print("❌ Ошибка: NOTION_MEETING_PAGE_ID не установлен в переменных окружения")
        return
    
    # Запуск основной функции
    # Примечание: get_latest_meeting_notes возвращает (block_id, title, content)
    result = await notion.get_latest_meeting_notes(page_id)
    
    print("\n📝 РЕЗУЛЬТАТ:")
    print("-" * 40)
    # Выводим контент (третий элемент кортежа)
    if isinstance(result, tuple):
        print(f"Заголовок: {result[1]}")
        print(f"Контент:\n{result[2]}")
    else:
        print(result)
    print("-" * 40)

if __name__ == "__main__":
    asyncio.run(main())
