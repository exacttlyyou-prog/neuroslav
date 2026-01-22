"""
Локальный MCP сервер Notion для получения meeting-notes.
Запускает @notionhq/notion-mcp-server локально с токеном.
"""
import asyncio
import subprocess
import os
import httpx
import json
from typing import Optional, Dict, Any
from loguru import logger
from core.config import get_settings


class NotionLocalMCP:
    """Локальный MCP сервер Notion для получения meeting-notes."""
    
    def __init__(self):
        settings = get_settings()
        self.token = settings.notion_mcp_token or settings.notion_token
        if not self.token:
            raise ValueError("NOTION_TOKEN или NOTION_MCP_TOKEN не установлен")
        
        self.port = 3005
        self.auth_token = "local_mcp_token_12345"
        self.server_process = None
    
    async def start_server(self) -> bool:
        """Запускает локальный MCP сервер."""
        try:
            logger.info(f"Запуск локального MCP сервера на порту {self.port}...")
            
            # Запускаем сервер в фоне
            env = {
                **os.environ,
                "NOTION_TOKEN": self.token,
                "AUTH_TOKEN": self.auth_token
            }
            
            self.server_process = subprocess.Popen(
                ["npx", "-y", "@notionhq/notion-mcp-server", 
                 "--transport", "http",
                 "--port", str(self.port),
                 "--auth-token", self.auth_token],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Ждем, пока сервер запустится
            await asyncio.sleep(3)
            
            # Проверяем, что сервер работает
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"http://localhost:{self.port}/health")
                    if response.status_code == 200:
                        logger.info(f"✅ Локальный MCP сервер запущен на порту {self.port}")
                        return True
            except Exception:
                pass
            
            logger.warning("Локальный MCP сервер не отвечает")
            return False
        except Exception as e:
            logger.debug(f"Ошибка запуска локального MCP сервера: {e}")
            return False
    
    async def stop_server(self):
        """Останавливает локальный MCP сервер."""
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
                logger.info("Локальный MCP сервер остановлен")
            except Exception as e:
                logger.debug(f"Ошибка остановки сервера: {e}")
                if self.server_process:
                    self.server_process.kill()
    
    async def fetch_page(self, page_id: str) -> Optional[str]:
        """
        Получает контент страницы через локальный MCP сервер.
        """
        try:
            # Запускаем сервер, если еще не запущен
            if not self.server_process or self.server_process.poll() is not None:
                if not await self.start_server():
                    return None
            
            # Подключаемся к локальному MCP серверу
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Пробуем вызвать notion-fetch через локальный сервер
                # Но локальный сервер не имеет notion-fetch, поэтому используем API-get-block-children
                mcp_url = f"http://localhost:{self.port}/mcp"
                headers = {
                    "Authorization": f"Bearer {self.auth_token}",
                    "Content-Type": "application/json"
                }
                
                # Формируем MCP запрос для получения блоков
                request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "API-get-block-children",
                        "arguments": {
                            "block_id": page_id,
                            "page_size": 100
                        }
                    }
                }
                
                response = await client.post(mcp_url, headers=headers, json=request)
                if response.status_code == 200:
                    data = response.json()
                    # Извлекаем текст из результата
                    if "result" in data:
                        result = data["result"]
                        # Парсим результат и извлекаем текст
                        # (локальный MCP не может получить transcription, но может получить доступный контент)
                        return self._extract_text_from_mcp_result(result)
        except Exception as e:
            logger.debug(f"Ошибка получения данных через локальный MCP: {e}")
        
        return None
    
    def _extract_text_from_mcp_result(self, result: Any) -> str:
        """Извлекает текст из результата MCP."""
        # Локальный MCP не может получить transcription блоки
        # Но может вернуть доступный контент
        if isinstance(result, dict):
            if "content" in result:
                return str(result["content"])
            elif "text" in result:
                return str(result["text"])
        elif isinstance(result, str):
            return result
        return ""
