"""
Прямое получение контента страницы Notion через различные методы.
Пробует обойти ограничения API для получения transcription блоков.
"""
import httpx
import asyncio
from typing import Dict, Any, Optional
from loguru import logger
from core.config import get_settings


class NotionDirectFetcher:
    """Прямое получение контента из Notion, обходя ограничения API."""
    
    def __init__(self):
        settings = get_settings()
        self.token = settings.notion_mcp_token or settings.notion_token
        if not self.token:
            raise ValueError("NOTION_TOKEN или NOTION_MCP_TOKEN не установлен")
        
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2025-09-03",
            "Content-Type": "application/json"
        }
    
    async def fetch_page_content_direct(self, page_id: str) -> Optional[str]:
        """
        Пробует получить контент страницы напрямую через различные методы.
        
        Методы:
        1. Экспорт страницы в markdown
        2. Прямой запрос к странице с расширенными параметрами
        3. Получение всех блоков с обработкой ошибок
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Метод 1: Пробуем экспорт страницы
            try:
                logger.info("Попытка экспорта страницы в markdown...")
                # Notion не имеет публичного API для экспорта, но пробуем
                # Альтернатива: используем прямой запрос к странице
                pass
            except Exception as e:
                logger.debug(f"Экспорт недоступен: {e}")
            
            # Метод 2: Получаем страницу и все её блоки с обработкой ошибок
            try:
                logger.info("Получение страницы и блоков с обработкой ошибок...")
                
                # Получаем информацию о странице
                page_response = await client.get(
                    f"{self.base_url}/pages/{page_id}",
                    headers=self.headers
                )
                page_response.raise_for_status()
                page_data = page_response.json()
                
                # Пробуем получить все блоки, пропуская transcription
                all_content_parts = []
                cursor = None
                transcription_count = 0
                
                while True:
                    try:
                        blocks_response = await client.get(
                            f"{self.base_url}/blocks/{page_id}/children",
                            headers=self.headers,
                            params={"page_size": 100, "start_cursor": cursor} if cursor else {"page_size": 100}
                        )
                        blocks_response.raise_for_status()
                        blocks_data = blocks_response.json()
                        
                        blocks = blocks_data.get("results", [])
                        for block in blocks:
                            block_type = block.get("type")
                            
                            # Пропускаем unsupported блоки, но сохраняем информацию
                            if block_type == "unsupported":
                                transcription_count += 1
                                logger.debug(f"Пропущен unsupported блок (transcription #{transcription_count})")
                                continue
                            
                            # Извлекаем текст из доступных блоков
                            if block_type in ["paragraph", "heading_1", "heading_2", "heading_3"]:
                                rich_text = block.get(block_type, {}).get("rich_text", [])
                                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                                if text:
                                    if block_type.startswith("heading"):
                                        level = block_type.split("_")[1]
                                        text = f"{'#' * int(level)} {text}"
                                    all_content_parts.append(text)
                        
                        if not blocks_data.get("has_more"):
                            break
                        cursor = blocks_data.get("next_cursor")
                        
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 400 and "transcription" in str(e.response.text).lower():
                            logger.debug(f"Пропущен transcription блок на позиции курсора {cursor}")
                            # Пробуем пропустить проблемный блок, получив следующий курсор другим способом
                            # Это сложно без знания структуры, поэтому просто пропускаем
                            break
                        raise
                
                if all_content_parts:
                    content = "\n\n".join(all_content_parts)
                    logger.info(f"✅ Получен контент: {len(content)} символов (пропущено transcription блоков: {transcription_count})")
                    return content
                else:
                    logger.warning(f"Контент не получен (пропущено transcription блоков: {transcription_count})")
                    
            except Exception as e:
                logger.debug(f"Ошибка при прямом получении: {e}")
        
        return None
    
    async def try_alternative_endpoints(self, page_id: str) -> Optional[str]:
        """
        Пробует альтернативные эндпоинты для получения контента.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Пробуем разные варианты эндпоинтов
            endpoints_to_try = [
                f"{self.base_url}/pages/{page_id}/export",
                f"{self.base_url}/pages/{page_id}/content",
                f"{self.base_url}/pages/{page_id}/markdown",
            ]
            
            for endpoint in endpoints_to_try:
                try:
                    logger.debug(f"Пробуем эндпоинт: {endpoint}")
                    response = await client.get(endpoint, headers=self.headers)
                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, dict):
                            text = data.get("content") or data.get("markdown") or data.get("text") or str(data)
                        else:
                            text = str(data)
                        if text and len(text) > 50:
                            logger.info(f"✅ Получен контент через {endpoint}: {len(text)} символов")
                            return text
                except Exception as e:
                    logger.debug(f"Эндпоинт {endpoint} недоступен: {e}")
                    continue
        
        return None
