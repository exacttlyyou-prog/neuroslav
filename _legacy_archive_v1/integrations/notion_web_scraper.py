"""
Веб-скрапинг страницы Notion для получения meeting-notes.
Использует прямые HTTP запросы с правильными заголовками для получения полного контента.
"""
import httpx
import re
import json
from typing import Optional, Dict, Any
from loguru import logger
from core.config import get_settings


class NotionWebScraper:
    """Веб-скрапинг страниц Notion для получения meeting-notes."""
    
    def __init__(self):
        settings = get_settings()
        self.token = settings.notion_mcp_token or settings.notion_token
        if not self.token:
            raise ValueError("NOTION_TOKEN или NOTion_MCP_TOKEN не установлен")
    
    async def get_page_with_full_content(self, page_id: str) -> Optional[str]:
        """
        Получает полный контент страницы через разные методы.
        Пробует экспорт страницы и прямой API запрос с расширенными параметрами.
        """
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": "2025-09-03",
                "Content-Type": "application/json"
            }
            
            # Метод 1: Пробуем экспорт страницы в markdown
            try:
                logger.debug("Пробуем экспорт страницы в markdown...")
                export_url = f"https://api.notion.com/v1/pages/{page_id}/export"
                response = await client.post(
                    export_url,
                    headers=headers,
                    json={"format": "markdown"}
                )
                if response.status_code == 200:
                    export_data = response.json()
                    if isinstance(export_data, dict):
                        content = export_data.get("content") or export_data.get("markdown") or str(export_data)
                        if content and len(content.strip()) >= 100:
                            logger.info(f"✅ Получен контент через экспорт: {len(content)} символов")
                            return content
            except Exception as e:
                logger.debug(f"Экспорт недоступен: {e}")
            
            # Метод 2: Прямой запрос к API с расширенными параметрами
            try:
                logger.debug("Пробуем прямой API запрос с расширенными параметрами...")
                # Получаем страницу
                page_response = await client.get(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    headers=headers
                )
                if page_response.status_code == 200:
                    page_data = page_response.json()
                    
                    # Пробуем получить блоки с разными параметрами
                    blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
                    
                    # Пробуем получить все блоки, включая те, что могут содержать данные
                    blocks_response = await client.get(
                        blocks_url,
                        headers=headers,
                        params={"page_size": 100}
                    )
                    
                    if blocks_response.status_code == 200:
                        blocks_data = blocks_response.json()
                        blocks = blocks_data.get("results", [])
                        
                        # Извлекаем текст из всех доступных блоков
                        content_parts = []
                        for block in blocks:
                            block_type = block.get("type")
                            if block_type == "unsupported":
                                continue
                            
                            # Извлекаем текст
                            if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
                                rich_text = block.get(block_type, {}).get("rich_text", [])
                                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                                if text:
                                    if block_type.startswith("heading"):
                                        level = block_type.split("_")[1]
                                        text = f"{'#' * int(level)} {text}"
                                    content_parts.append(text)
                        
                        if content_parts:
                            content = "\n\n".join(content_parts)
                            if len(content.strip()) >= 100:
                                logger.info(f"✅ Получен контент через API: {len(content)} символов")
                                return content
            except Exception as e:
                logger.debug(f"API запрос: {e}")
            
            # Метод 3: Веб-скрапинг HTML
            try:
                logger.debug("Пробуем веб-скрапинг HTML...")
                page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
                web_headers = {
                    **headers,
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
                
                response = await client.get(page_url, headers=web_headers)
                if response.status_code == 200:
                    html = response.text
                    
                    # Ищем JSON данные
                    content = self._extract_content_from_html(html)
                    if content and len(content.strip()) >= 100:
                        logger.info(f"✅ Извлечен контент из HTML: {len(content)} символов")
                        return content
                    
                    # Парсим HTML напрямую
                    content = self._parse_html_for_meeting_notes(html)
                    if content and len(content.strip()) >= 100:
                        logger.info(f"✅ Извлечен контент из HTML (парсинг): {len(content)} символов")
                        return content
            except Exception as e:
                logger.debug(f"Веб-скрапинг HTML: {e}")
        
        return None
    
    def _extract_content_from_html(self, html: str) -> Optional[str]:
        """Извлекает контент из JSON данных в HTML."""
        # Ищем JSON в script тегах (более агрессивный поиск)
        patterns = [
            r'<script[^>]*id="notion-app-data"[^>]*>(.*?)</script>',
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
            r'notion-page-data\s*=\s*({.*?});',
            r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
            r'window\.__INITIAL_DATA__\s*=\s*({.*?});',
            r'notion\.initialData\s*=\s*({.*?});',
        ]
        
        all_meeting_data = {}
        
        for pattern in patterns:
            matches = re.finditer(pattern, html, re.DOTALL)
            for match in matches:
                try:
                    json_str = match.group(1).strip()
                    # Убираем комментарии и лишние символы
                    json_str = re.sub(r'//.*?\n', '\n', json_str)
                    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
                    
                    data = json.loads(json_str)
                    
                    # Рекурсивно ищем meeting-notes данные
                    meeting_data = self._find_meeting_in_json(data)
                    if meeting_data:
                        all_meeting_data.update(meeting_data)
                except (json.JSONDecodeError, Exception) as e:
                    logger.debug(f"Ошибка парсинга JSON (паттерн {pattern[:30]}...): {e}")
                    continue
        
        if all_meeting_data:
            return self._format_meeting_content(all_meeting_data)
        
        return None
    
    def _find_meeting_in_json(self, data: Any, depth: int = 0) -> Optional[Dict[str, Any]]:
        """Рекурсивно ищет meeting-notes данные в JSON."""
        if depth > 25:
            return None
        
        if isinstance(data, dict):
            # Ищем ключи, связанные с meeting/transcript/summary
            meeting_data = {}
            
            for key, value in data.items():
                key_lower = str(key).lower()
                
                # Ищем summary, transcript, notes
                if "summary" in key_lower and isinstance(value, str) and len(value) > 50:
                    meeting_data["summary"] = value
                elif "transcript" in key_lower and isinstance(value, str) and len(value) > 100:
                    meeting_data["transcript"] = value
                elif "notes" in key_lower and isinstance(value, str) and len(value) > 50:
                    meeting_data["notes"] = value
                elif "meeting" in key_lower and isinstance(value, str) and len(value) > 100:
                    meeting_data["content"] = value
                elif isinstance(value, (dict, list)):
                    # Рекурсивный поиск в вложенных структурах
                    result = self._find_meeting_in_json(value, depth + 1)
                    if result:
                        meeting_data.update(result)
            
            if meeting_data:
                return meeting_data
            
            # Если не нашли напрямую, продолжаем рекурсивный поиск
            for value in data.values():
                if isinstance(value, (dict, list)):
                    result = self._find_meeting_in_json(value, depth + 1)
                    if result:
                        return result
        
        elif isinstance(data, list):
            for item in data:
                result = self._find_meeting_in_json(item, depth + 1)
                if result:
                    return result
        
        return None
    
    def _format_meeting_content(self, meeting_data: Dict[str, Any]) -> str:
        """Форматирует данные встречи в читаемый текст."""
        content_parts = []
        
        if "summary" in meeting_data:
            content_parts.append(f"## Summary\n{meeting_data['summary']}")
        
        if "transcript" in meeting_data:
            content_parts.append(f"## Transcript\n{meeting_data['transcript']}")
        
        if "notes" in meeting_data:
            content_parts.append(f"## Notes\n{meeting_data['notes']}")
        
        if "content" in meeting_data:
            content_parts.append(str(meeting_data['content']))
        
        return "\n\n".join(content_parts) if content_parts else ""
    
    def _parse_html_for_meeting_notes(self, html: str) -> Optional[str]:
        """Парсит HTML напрямую для поиска meeting-notes."""
        # Убираем script и style теги
        clean_html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        clean_html = re.sub(r'<style[^>]*>.*?</style>', '', clean_html, flags=re.DOTALL | re.IGNORECASE)
        
        # Ищем структурированные данные (более агрессивный поиск)
        patterns = [
            # Summary
            r'(?:summary|Summary|SUMMARY)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-()]{300,8000})',
            # Transcript
            r'(?:transcript|Transcript|TRANSCRIPT)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-()]{500,15000})',
            # Meeting notes
            r'(?:meeting\s+notes?|Meeting\s+Notes?)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-()]{300,8000})',
            # Ищем данные в data-атрибутах
            r'data-summary=["\']([^"\']{200,5000})["\']',
            r'data-transcript=["\']([^"\']{500,10000})["\']',
        ]
        
        content_parts = []
        found_sections = {}
        
        for pattern in patterns:
            matches = re.finditer(pattern, clean_html, re.IGNORECASE | re.DOTALL)
            for match in matches:
                text = match.group(1)
                # Очищаем от HTML тегов
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'&[a-z]+;', ' ', text)  # HTML entities
                text = re.sub(r'\s+', ' ', text).strip()
                
                # Пропускаем JavaScript и служебные строки
                if any(kw in text for kw in ['function', 'var ', 'const ', 'window.', 'document.', 'JSON.stringify']):
                    continue
                
                # Проверяем, что это реальный текст (содержит слова)
                words = text.split()
                if len(words) < 20:
                    continue
                
                # Определяем тип секции
                if 'summary' in pattern.lower():
                    found_sections['summary'] = text
                elif 'transcript' in pattern.lower():
                    found_sections['transcript'] = text
                elif 'meeting' in pattern.lower():
                    found_sections['meeting'] = text
                else:
                    content_parts.append(text)
        
        # Формируем структурированный контент
        if found_sections:
            result_parts = []
            if 'summary' in found_sections:
                result_parts.append(f"## Summary\n{found_sections['summary']}")
            if 'transcript' in found_sections:
                result_parts.append(f"## Transcript\n{found_sections['transcript']}")
            if 'meeting' in found_sections:
                result_parts.append(f"## Meeting Notes\n{found_sections['meeting']}")
            if result_parts:
                return "\n\n".join(result_parts)
        
        if content_parts:
            return "\n\n".join(content_parts)
        
        return None
    
    def _extract_text_from_blocks(self, blocks: list) -> str:
        """Извлекает текст из блоков Notion API."""
        content_parts = []
        
        for block in blocks:
            block_type = block.get("type")
            if block_type == "unsupported":
                continue
            
            # Извлекаем текст из блока
            if block_type in ["paragraph", "heading_1", "heading_2", "heading_3"]:
                rich_text = block.get(block_type, {}).get("rich_text", [])
                text = "".join([rt.get("plain_text", "") for rt in rich_text])
                if text:
                    if block_type.startswith("heading"):
                        level = block_type.split("_")[1]
                        text = f"{'#' * int(level)} {text}"
                    content_parts.append(text)
        
        return "\n\n".join(content_parts)
