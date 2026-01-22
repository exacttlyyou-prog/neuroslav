"""
Прямой запрос к Notion API для получения всех доступных данных страницы.
Использует различные методы для извлечения meeting-notes.
"""
import httpx
import json
from typing import Optional, Dict, Any
from loguru import logger
from core.config import get_settings


class NotionDirectAPI:
    """Прямой запрос к Notion API для получения meeting-notes."""
    
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
    
    async def get_page_all_data(self, page_id: str) -> Optional[str]:
        """
        Получает все доступные данные страницы через прямой API запрос.
        Пробует разные методы для получения meeting-notes.
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Метод 1: Получаем страницу и все её свойства
            try:
                page_response = await client.get(
                    f"{self.base_url}/pages/{page_id}",
                    headers=self.headers
                )
                if page_response.status_code == 200:
                    page_data = page_response.json()
                    
                    # Извлекаем текст из свойств страницы (включая все типы свойств)
                    content_parts = []
                    if "properties" in page_data:
                        for prop_name, prop_val in page_data["properties"].items():
                            prop_type = prop_val.get("type")
                            
                            # Заголовок
                            if prop_type == "title":
                                title_parts = prop_val.get("title", [])
                                if title_parts:
                                    title_text = "".join([rt.get("plain_text", "") for rt in title_parts])
                                    if title_text:
                                        content_parts.append(f"# {title_text}")
                            
                            # Rich text свойства (могут содержать summary/notes)
                            if prop_type in ["rich_text", "text"]:
                                rich_text = prop_val.get(prop_type, [])
                                if rich_text:
                                    text = "".join([rt.get("plain_text", "") for rt in rich_text])
                                    if text and len(text) > 50:
                                        # Если название свойства содержит meeting/summary/notes, добавляем заголовок
                                        if any(kw in prop_name.lower() for kw in ["meeting", "summary", "notes", "transcript"]):
                                            content_parts.append(f"## {prop_name}\n{text}")
                                        else:
                                            content_parts.append(text)
                            
                            # Formula свойства (могут содержать вычисляемые значения)
                            if prop_type == "formula":
                                formula_result = prop_val.get("formula", {})
                                if formula_result.get("type") == "string":
                                    formula_text = formula_result.get("string", "")
                                    if formula_text and len(formula_text) > 50:
                                        content_parts.append(formula_text)
                            
                            # Rollup свойства (могут содержать агрегированные данные)
                            if prop_type == "rollup":
                                rollup_result = prop_val.get("rollup", {})
                                if rollup_result.get("type") == "array":
                                    array_items = rollup_result.get("array", [])
                                    for item in array_items:
                                        if item.get("type") == "title":
                                            title_parts = item.get("title", [])
                                            if title_parts:
                                                text = "".join([rt.get("plain_text", "") for rt in title_parts])
                                                if text:
                                                    content_parts.append(f"- {text}")
                    
                    # Метод 2: Получаем все блоки страницы
                    blocks_url = f"{self.base_url}/blocks/{page_id}/children"
                    cursor = None
                    all_blocks = []
                    
                    while True:
                        params = {"page_size": 100}
                        if cursor:
                            params["start_cursor"] = cursor
                        
                        blocks_response = await client.get(blocks_url, headers=self.headers, params=params)
                        if blocks_response.status_code != 200:
                            break
                        
                        blocks_data = blocks_response.json()
                        blocks = blocks_data.get("results", [])
                        all_blocks.extend(blocks)
                        
                        if not blocks_data.get("has_more"):
                            break
                        cursor = blocks_data.get("next_cursor")
                    
                    # Извлекаем текст из всех блоков (рекурсивно для вложенных блоков)
                    transcription_count = 0
                    for block in all_blocks:
                        block_type = block.get("type")
                        if block_type == "unsupported":
                            transcription_count += 1
                            logger.debug(f"Пропущен unsupported блок #{transcription_count}")
                            continue
                        
                        # Извлекаем текст из блока
                        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", 
                                         "bulleted_list_item", "numbered_list_item", "to_do",
                                         "quote", "callout", "toggle", "code"]:
                            block_data = block.get(block_type, {})
                            rich_text = block_data.get("rich_text", [])
                            text = "".join([rt.get("plain_text", "") for rt in rich_text])
                            
                            if text:
                                if block_type.startswith("heading"):
                                    level = block_type.split("_")[1]
                                    text = f"{'#' * int(level)} {text}"
                                elif block_type == "quote":
                                    text = f"> {text}"
                                elif block_type == "callout":
                                    icon = block_data.get("icon", {}).get("emoji", "💡")
                                    text = f"{icon} {text}"
                                elif block_type == "code":
                                    language = block_data.get("language", "")
                                    text = f"```{language}\n{text}\n```"
                                
                                content_parts.append(text)
                        
                        # Рекурсивно получаем дочерние блоки
                        if block.get("has_children"):
                            try:
                                block_id = block.get("id")
                                children_response = await client.get(
                                    f"{self.base_url}/blocks/{block_id}/children",
                                    headers=self.headers,
                                    params={"page_size": 100}
                                )
                                if children_response.status_code == 200:
                                    children_data = children_response.json()
                                    for child_block in children_data.get("results", []):
                                        child_type = child_block.get("type")
                                        if child_type == "unsupported":
                                            transcription_count += 1
                                            continue
                                        
                                        if child_type in ["paragraph", "heading_1", "heading_2", "heading_3"]:
                                            child_data = child_block.get(child_type, {})
                                            child_rich_text = child_data.get("rich_text", [])
                                            child_text = "".join([rt.get("plain_text", "") for rt in child_rich_text])
                                            if child_text:
                                                content_parts.append(f"  {child_text}")  # Отступ для вложенных блоков
                            except Exception:
                                pass
                    
                    if transcription_count > 0:
                        logger.warning(f"Обнаружено {transcription_count} transcription блоков, но они недоступны через API")
                    
                    if content_parts:
                        content = "\n\n".join(content_parts)
                        if len(content.strip()) >= 50:  # Снижаем порог, чтобы получить хотя бы что-то
                            logger.info(f"✅ Получен контент через прямой API: {len(content)} символов (пропущено transcription: {transcription_count})")
                            return content
            except Exception as e:
                logger.debug(f"Прямой API запрос: {e}")
        
        return None
