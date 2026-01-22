"""
Прямой вызов notion-fetch через HTTP запрос к MCP серверу Notion.
Пробует использовать токен для прямого доступа к notion-fetch инструменту.
"""
import httpx
import json
from typing import Dict, Any, Optional
from loguru import logger
from core.config import get_settings


class NotionMCPDirect:
    """Прямой вызов notion-fetch через HTTP."""
    
    def __init__(self):
        settings = get_settings()
        self.token = settings.notion_mcp_token or settings.notion_token
        if not self.token:
            raise ValueError("NOTION_TOKEN или NOTION_MCP_TOKEN не установлен")
    
    async def fetch_page_via_direct_mcp_call(self, page_id: str) -> Optional[str]:
        """
        Пробует вызвать notion-fetch напрямую через HTTP запрос к MCP серверу.
        
        Пробует разные варианты:
        1. Прямой POST запрос к /mcp/tools/notion-fetch
        2. Использование токена как OAuth токена
        3. Пробует разные форматы авторизации
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Вариант 1: Пробуем прямой вызов к MCP endpoint
            mcp_endpoints = [
                "https://mcp.notion.com/mcp/tools/notion-fetch",
                "https://mcp.notion.com/tools/notion-fetch",
                "https://mcp.notion.com/api/notion-fetch",
                "https://mcp.notion.com/notion-fetch",
            ]
            
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": "2025-09-03",
                "Content-Type": "application/json"
            }
            
            # Пробуем с URL страницы
            page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
            
            for endpoint in mcp_endpoints:
                try:
                    logger.debug(f"Пробуем эндпоинт: {endpoint}")
                    response = await client.post(
                        endpoint,
                        headers=headers,
                        json={"url": page_url}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        text = data.get("content") or data.get("text") or str(data)
                        if text and len(text) > 50:
                            logger.info(f"✅ Получен контент через прямой MCP вызов: {len(text)} символов")
                            return text
                except Exception as e:
                    logger.debug(f"Эндпоинт {endpoint} недоступен: {e}")
                    continue
            
            # Вариант 2: Пробуем с ID вместо URL
            for endpoint in mcp_endpoints:
                try:
                    response = await client.post(
                        endpoint,
                        headers=headers,
                        json={"id": page_id}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        text = data.get("content") or data.get("text") or str(data)
                        if text and len(text) > 50:
                            logger.info(f"✅ Получен контент через прямой MCP вызов (ID): {len(text)} символов")
                            return text
                except Exception as e:
                    logger.debug(f"Эндпоинт {endpoint} с ID недоступен: {e}")
                    continue
        
        return None
