"""
Тест токена для подключения к Notion.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from notion_client import AsyncClient
from core.config import get_settings
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO", format="<level>{message}</level>")

async def test_token():
    """Тестируем токен с обычным Notion API."""
    settings = get_settings()
    mcp_token = settings.notion_mcp_token
    
    if not mcp_token:
        print("❌ NOTION_MCP_TOKEN не установлен")
        return
    
    print(f"🔑 Тестируем токен: {mcp_token[:20]}...")
    
    # Пробуем использовать токен как обычный Notion API токен
    try:
        client = AsyncClient(auth=mcp_token)
        
        # Пробуем получить информацию о пользователе
        user = await client.users.me()
        print(f"✅ Токен работает! Пользователь: {user.get('name', 'Unknown')}")
        
        # Пробуем получить страницу
        page_id = "2edfa7fd637180b98715fa9f348f90f9"
        page = await client.pages.retrieve(page_id)
        print(f"✅ Страница получена: {page.get('url', 'N/A')}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка при использовании токена: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_token())
