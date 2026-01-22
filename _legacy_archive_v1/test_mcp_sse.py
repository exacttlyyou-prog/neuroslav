"""
Тест подключения к MCP Notion через SSE (для Cursor).
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from integrations.mcp_client import MCPNotionClient
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="DEBUG", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

PAGE_IDS = [
    "2edfa7fd637180b98715fa9f348f90f9",
    "ce32758331a5406694f86b8bd292605a",
]

async def main():
    print("🚀 Тест подключения к MCP Notion через SSE...\n")
    
    mcp_client = MCPNotionClient()
    
    for page_id in PAGE_IDS:
        print(f"{'='*60}")
        print(f"📄 Страница: {page_id}")
        print(f"{'='*60}\n")
        
        result = await mcp_client.fetch_page_via_remote_mcp(page_id, timeout=60)
        
        if result:
            text = result.get("text", "")
            print(f"✅ Успешно получен контент: {len(text)} символов")
            print(f"\nПервые 500 символов:\n{text[:500]}...\n")
        else:
            print("❌ Контент не получен\n")

if __name__ == "__main__":
    asyncio.run(main())
