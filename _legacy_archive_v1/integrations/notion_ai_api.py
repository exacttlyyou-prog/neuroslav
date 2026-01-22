"""
Интеграция с Notion AI API для получения transcription блоков.
Использует недокументированные эндпоинты для доступа к AI meeting notes.
"""
import httpx
from typing import Dict, Any, Optional
from loguru import logger
from core.config import get_settings


class NotionAIApiClient:
    """Клиент для работы с Notion AI API (недокументированные эндпоинты)."""
    
    def __init__(self):
        settings = get_settings()
        self.token = settings.notion_token or settings.notion_mcp_token
        if not self.token:
            raise ValueError("NOTION_TOKEN или NOTION_MCP_TOKEN не установлен")
        
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2025-09-03",
            "Content-Type": "application/json"
        }
    
    async def get_page_with_ai_content(
        self, page_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Получает страницу с AI контентом через недокументированные эндпоинты.
        
        Пробует разные варианты:
        1. /blocks/{block_id}/children с параметром для AI контента
        2. /pages/{page_id} с расширенными параметрами
        3. Специальный эндпоинт для view/transcription
        4. Экспорт страницы через /export
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Вариант 1: Пробуем экспорт страницы (может содержать AI контент)
            try:
                logger.info(f"Попытка экспорта страницы {page_id}...")
                export_response = await client.post(
                    f"{self.base_url}/pages/{page_id}/export",
                    headers={**self.headers, "Accept": "application/json"},
                    json={"format": "markdown"}
                )
                if export_response.status_code == 200:
                    export_data = export_response.json()
                    logger.info("✅ Экспорт страницы успешен")
                    return {"export": export_data, "type": "export"}
            except Exception as export_error:
                logger.debug(f"Экспорт недоступен: {export_error}")
            
            # Вариант 2: Пробуем получить страницу с расширенными параметрами
            try:
                logger.info(f"Попытка получить страницу {page_id} через AI API...")
                
                # Пробуем стандартный эндпоинт страницы
                response = await client.get(
                    f"{self.base_url}/pages/{page_id}",
                    headers=self.headers
                )
                response.raise_for_status()
                page_data = response.json()
                
                # Пробуем получить блоки с разными параметрами
                for params_variant in [
                    {"page_size": 100},
                    {"page_size": 100, "include_ai": "true"},
                    {"page_size": 100, "expand": "transcription"},
                ]:
                    try:
                        blocks_response = await client.get(
                            f"{self.base_url}/blocks/{page_id}/children",
                            headers=self.headers,
                            params=params_variant
                        )
                        if blocks_response.status_code == 200:
                            blocks_data = blocks_response.json()
                            blocks = blocks_data.get("results", [])
                            
                            # Ищем transcription блоки
                            transcription_content = []
                            for block in blocks:
                                block_type = block.get("type")
                                
                                if block_type == "unsupported":
                                    unsupported_type = block.get("unsupported", {}).get("type", "")
                                    if "transcription" in unsupported_type.lower() or "meeting" in unsupported_type.lower():
                                        block_id = block.get("id")
                                        
                                        # Пробуем разные эндпоинты для получения контента
                                        for endpoint_variant in [
                                            f"{self.base_url}/blocks/{block_id}/view",
                                            f"{self.base_url}/blocks/{block_id}/transcript",
                                            f"{self.base_url}/blocks/{block_id}/content",
                                        ]:
                                            try:
                                                content_response = await client.get(
                                                    endpoint_variant,
                                                    headers=self.headers
                                                )
                                                if content_response.status_code == 200:
                                                    content_data = content_response.json()
                                                    transcription_content.append(content_data)
                                                    logger.info(f"✅ Получен контент через {endpoint_variant}")
                                                    break
                                            except Exception:
                                                continue
                            
                            if transcription_content:
                                return {
                                    "page": page_data,
                                    "transcription_blocks": transcription_content,
                                    "blocks": blocks
                                }
                    except Exception as blocks_error:
                        logger.debug(f"Ошибка при получении блоков: {blocks_error}")
                        continue
                
            except httpx.HTTPStatusError as e:
                logger.debug(f"HTTP ошибка: {e.response.status_code} - {e.response.text}")
            except Exception as e:
                logger.debug(f"Ошибка при получении AI контента: {e}")
        
        return None
    
    async def get_transcription_content(
        self, page_id: str
    ) -> Optional[str]:
        """
        Извлекает текст из transcription блоков страницы.
        
        Returns:
            Текст контента или None
        """
        data = await self.get_page_with_ai_content(page_id)
        if not data:
            return None
        
        content_parts = []
        
        # Извлекаем контент из transcription блоков
        for block_data in data.get("transcription_blocks", []):
            # Пробуем разные пути к контенту
            if isinstance(block_data, dict):
                # Ищем текст в разных местах
                text = (
                    block_data.get("text") or
                    block_data.get("content") or
                    block_data.get("transcript") or
                    block_data.get("summary") or
                    str(block_data)
                )
                if text and isinstance(text, str):
                    content_parts.append(text)
        
        # Также пробуем извлечь из обычных блоков
        for block in data.get("blocks", []):
            block_type = block.get("type")
            if block_type in ["paragraph", "heading_1", "heading_2", "heading_3"]:
                rich_text = block.get(block_type, {}).get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                if text:
                    content_parts.append(text)
        
        return "\n\n".join(content_parts) if content_parts else None
