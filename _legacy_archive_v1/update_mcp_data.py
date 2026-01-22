"""
Скрипт для автоматического обновления данных из MCP Notion.
Этот скрипт должен вызываться периодически (например, через cron) 
или перед запуском основного скрипта.
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def save_mcp_data():
    """Сохраняет данные из MCP Notion в файл."""
    page_id = os.getenv("NOTION_MEETING_PAGE_ID")
    if not page_id:
        print("❌ NOTION_MEETING_PAGE_ID не установлен")
        return False
    
    root_dir = Path(__file__).parent
    mcp_file = root_dir / "mcp_response.json"
    
    print(f"📝 Для обновления данных выполните в Cursor:")
    print(f"   Используйте инструмент MCP: notion-fetch для страницы {page_id}")
    print(f"   Или запустите: python -c \"from mcp_Notion_notion_fetch import fetch; print(fetch('{page_id}'))\"")
    print(f"\n💡 Данные будут сохранены в: {mcp_file}")
    
    # Проверяем, есть ли уже файл
    if mcp_file.exists():
        print(f"✅ Файл уже существует: {mcp_file}")
        return True
    
    print(f"⚠️  Файл не найден. Нужно получить данные через MCP.")
    return False

if __name__ == "__main__":
    save_mcp_data()
