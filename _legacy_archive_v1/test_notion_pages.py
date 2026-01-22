"""
Тестовый скрипт для проверки получения контента из Notion страниц.
Проверяет оба способа: через MCP и через обычный API.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from services.notion_service import NotionService
from integrations.mcp_client import MCPNotionClient
from loguru import logger

# Настройка логирования
logger.remove()
logger.add(sys.stderr, level="DEBUG", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>")

# ID страниц из ссылок
PAGE_IDS = [
    "2edfa7fd637180b98715fa9f348f90f9",  # https://www.notion.so/2026-2edfa7fd637180b98715fa9f348f90f9
    "ce32758331a5406694f86b8bd292605a",  # https://www.notion.so/AI-Context-ce32758331a5406694f86b8bd292605a
]

async def test_mcp_direct(page_id: str):
    """Тест прямого подключения через MCP."""
    print(f"\n{'='*60}")
    print(f"🔍 Тест MCP для страницы: {page_id}")
    print(f"{'='*60}")
    
    mcp_client = MCPNotionClient()
    result = await mcp_client.fetch_page(page_id, timeout=60)
    
    if result:
        text = result.get("text", "")
        print(f"✅ MCP успешно получил контент: {len(text)} символов")
        print(f"\nПервые 500 символов:\n{text[:500]}...")
        return True
    else:
        print("❌ MCP не вернул контент")
        return False

async def test_notion_service(page_id: str):
    """Тест через NotionService."""
    print(f"\n{'='*60}")
    print(f"🔍 Тест NotionService для страницы: {page_id}")
    print(f"{'='*60}")
    
    try:
        notion = NotionService()
        
        # Проверяем тип объекта
        object_type = await notion._check_object_type(page_id)
        print(f"📋 Тип объекта: {object_type}")
        
        if object_type == "database":
            print("📊 Это база данных, используем get_latest_from_database()")
            page_id_result, title, content = await notion.get_latest_from_database(page_id)
        else:
            print("📄 Это страница, используем get_latest_meeting_notes()")
            page_id_result, title, content = await notion.get_latest_meeting_notes(page_id)
        
        if content and len(content.strip()) >= 50:
            print(f"✅ NotionService успешно получил контент: '{title}' ({len(content)} символов)")
            print(f"\nПервые 500 символов:\n{content[:500]}...")
            return True
        else:
            print(f"❌ NotionService вернул пустой или короткий контент: {len(content) if content else 0} символов")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка в NotionService: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("🚀 Запуск тестов для Notion страниц...")
    print(f"📝 Тестируем {len(PAGE_IDS)} страниц")
    
    results = {}
    
    for page_id in PAGE_IDS:
        print(f"\n{'#'*60}")
        print(f"📄 Страница ID: {page_id}")
        print(f"{'#'*60}")
        
        # Тест 1: Прямой MCP
        mcp_success = await test_mcp_direct(page_id)
        
        # Тест 2: NotionService
        service_success = await test_notion_service(page_id)
        
        results[page_id] = {
            "mcp": mcp_success,
            "service": service_success
        }
        
        # Небольшая пауза между страницами
        await asyncio.sleep(2)
    
    # Итоги
    print(f"\n{'='*60}")
    print("📊 ИТОГИ ТЕСТОВ")
    print(f"{'='*60}")
    
    for page_id, result in results.items():
        print(f"\nСтраница {page_id}:")
        print(f"  MCP:        {'✅' if result['mcp'] else '❌'}")
        print(f"  NotionService: {'✅' if result['service'] else '❌'}")

if __name__ == "__main__":
    asyncio.run(main())
