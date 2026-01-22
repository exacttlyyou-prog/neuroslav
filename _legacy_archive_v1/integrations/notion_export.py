"""
Экспорт страницы Notion для получения meeting-notes.
Пробует использовать экспорт страницы через разные методы.
"""
import httpx
import json
from typing import Optional
from loguru import logger
from core.config import get_settings


class NotionExporter:
    """Экспорт страниц Notion для получения meeting-notes."""
    
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
    
    async def export_page(self, page_id: str) -> Optional[str]:
        """
        Экспортирует страницу для получения полного контента, включая transcription блоки.
        Пробует разные методы: внутренний API, экспорт через API, веб-скрапинг.
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Метод 1: Используем внутренний API Notion /api/v3/loadPageChunk
            # Этот API может возвращать больше данных, включая transcription блоки
            # Этот API может возвращать больше данных, включая transcription блоки
            try:
                logger.debug("Пробуем внутренний API Notion loadPageChunk...")
                api_url = "https://www.notion.so/api/v3/loadPageChunk"
                
                # Преобразуем page_id в правильный формат (без дефисов)
                page_id_clean = page_id.replace('-', '')
                
                # Пробуем разные варианты заголовков
                header_variants = [
                    {
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Cookie": f"token_v2={self.token}",
                    },
                    {
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.token}",
                        "Notion-Version": "2025-09-03",
                        "Cookie": f"token_v2={self.token}",
                    },
                ]
                
                payload = {
                    "pageId": page_id_clean,
                    "limit": 100,
                    "cursor": {"stack": []},
                    "chunkNumber": 0,
                    "verticalColumns": False
                }
                
                for headers in header_variants:
                    try:
                        response = await client.post(api_url, headers=headers, json=payload)
                        if response.status_code == 200:
                            data = response.json()
                            logger.debug(f"loadPageChunk вернул данные: {list(data.keys())}")
                            
                            # Извлекаем текст из recordMap
                            if "recordMap" in data:
                                content_parts = []
                                record_map = data["recordMap"]
                                
                                # Ищем блоки в recordMap
                                blocks = record_map.get("block", {})
                                logger.debug(f"Найдено блоков в recordMap: {len(blocks)}")
                                
                                for block_id, block_data in blocks.items():
                                    block_value = block_data.get("value", {})
                                    block_type = block_value.get("type")
                                    
                                    # Пробуем получить данные даже из unsupported блоков
                                    if block_type == "unsupported":
                                        # Пробуем извлечь данные из raw данных блока
                                        raw_data = block_data.get("value", {})
                                        if isinstance(raw_data, dict):
                                            # Ищем текст в разных полях (может содержать transcription данные)
                                            for key, value in raw_data.items():
                                                if isinstance(value, str) and len(value) > 100:
                                                    # Проверяем, что это не служебные данные
                                                    if not any(kw in value.lower() for kw in ['function', 'var ', 'const ', 'window.']):
                                                        content_parts.append(value)
                                        continue
                                    
                                    # Извлекаем текст из properties блока
                                    properties = block_value.get("properties", {})
                                    for prop_key, prop_value in properties.items():
                                        if isinstance(prop_value, list):
                                            for item in prop_value:
                                                if isinstance(item, list) and len(item) > 0:
                                                    text_parts = []
                                                    for sub_item in item:
                                                        if isinstance(sub_item, str):
                                                            text_parts.append(sub_item)
                                                        elif isinstance(sub_item, list) and len(sub_item) > 0:
                                                            text_parts.append(str(sub_item[0]))
                                                    
                                                    if text_parts:
                                                        text = " ".join(text_parts)
                                                        if text and len(text.strip()) > 50:
                                                            content_parts.append(text)
                                                elif isinstance(item, str) and len(item) > 50:
                                                    content_parts.append(item)
                                
                                if content_parts:
                                    content = "\n\n".join(content_parts)
                                    if len(content.strip()) >= 100:
                                        logger.info(f"✅ Получен контент через loadPageChunk: {len(content)} символов")
                                        return content
                        elif response.status_code == 401:
                            logger.debug("loadPageChunk требует авторизацию (token_v2 cookie)")
                            continue  # Переходим к следующему варианту заголовков
                        elif response.status_code == 400:
                            logger.debug(f"loadPageChunk вернул 400: {response.text[:200]}")
                    except Exception as variant_error:
                        logger.debug(f"Ошибка с вариантом заголовков: {variant_error}")
                        continue
            except Exception as e:
                logger.debug(f"loadPageChunk API: {e}")
            
            # Метод 2: Пробуем экспорт через API
            try:
                logger.debug("Пробуем экспорт страницы через API...")
                export_url = f"{self.base_url}/pages/{page_id}/export"
                
                # Пробуем разные форматы экспорта
                for export_format in ["markdown", "html", "pdf"]:
                    try:
                        response = await client.post(
                            export_url,
                            headers=self.headers,
                            json={"format": export_format}
                        )
                        if response.status_code == 200:
                            data = response.json()
                            content = data.get("content") or data.get("markdown") or data.get("html") or str(data)
                            if content and len(content.strip()) >= 100:
                                logger.info(f"✅ Экспорт успешен ({export_format}): {len(content)} символов")
                                return content
                    except Exception as e:
                        logger.debug(f"Экспорт в {export_format} недоступен: {e}")
                        continue
            except Exception as e:
                logger.debug(f"Экспорт через API: {e}")
            
            # Метод 3: Используем внутренний API Notion /api/v3/loadPageChunk
            # Этот API может возвращать больше данных, включая transcription блоки
            # Требует token_v2 cookie (из браузера), но пробуем с integration token
            try:
                logger.debug("Пробуем внутренний API Notion loadPageChunk...")
                api_url = "https://www.notion.so/api/v3/loadPageChunk"
                
                # Преобразуем page_id в правильный формат (без дефисов)
                page_id_clean = page_id.replace('-', '')
                
                # Пробуем разные варианты заголовков
                header_variants = [
                    {
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Cookie": f"token_v2={self.token}",
                    },
                    {
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.token}",
                        "Notion-Version": "2025-09-03",
                        "Cookie": f"token_v2={self.token}",
                    },
                ]
                
                payload = {
                    "pageId": page_id_clean,
                    "limit": 100,
                    "cursor": {"stack": []},
                    "chunkNumber": 0,
                    "verticalColumns": False
                }
                
                for headers in header_variants:
                    try:
                        response = await client.post(api_url, headers=headers, json=payload)
                        if response.status_code == 200:
                            data = response.json()
                            logger.debug(f"loadPageChunk вернул данные: {list(data.keys())}")
                            
                            # Извлекаем текст из recordMap
                            if "recordMap" in data:
                                content_parts = []
                                record_map = data["recordMap"]
                                
                                # Ищем блоки в recordMap
                                blocks = record_map.get("block", {})
                                logger.debug(f"Найдено блоков в recordMap: {len(blocks)}")
                                
                                for block_id, block_data in blocks.items():
                                    block_value = block_data.get("value", {})
                                    block_type = block_value.get("type")
                                    
                                    # Пробуем получить данные даже из unsupported блоков
                                    if block_type == "unsupported":
                                        # Пробуем извлечь данные из raw данных блока
                                        raw_data = block_data.get("value", {})
                                        if isinstance(raw_data, dict):
                                            # Ищем текст в разных полях (может содержать transcription данные)
                                            for key, value in raw_data.items():
                                                if isinstance(value, str) and len(value) > 100:
                                                    # Проверяем, что это не служебные данные
                                                    if not any(kw in value.lower() for kw in ['function', 'var ', 'const ', 'window.']):
                                                        content_parts.append(value)
                                        continue
                                    
                                    # Извлекаем текст из properties блока
                                    properties = block_value.get("properties", {})
                                    for prop_key, prop_value in properties.items():
                                        if isinstance(prop_value, list):
                                            for item in prop_value:
                                                if isinstance(item, list) and len(item) > 0:
                                                    text_parts = []
                                                    for sub_item in item:
                                                        if isinstance(sub_item, str):
                                                            text_parts.append(sub_item)
                                                        elif isinstance(sub_item, list) and len(sub_item) > 0:
                                                            text_parts.append(str(sub_item[0]))
                                                    
                                                    if text_parts:
                                                        text = " ".join(text_parts)
                                                        if text and len(text.strip()) > 50:
                                                            content_parts.append(text)
                                                elif isinstance(item, str) and len(item) > 50:
                                                    content_parts.append(item)
                                
                                if content_parts:
                                    content = "\n\n".join(content_parts)
                                    if len(content.strip()) >= 100:
                                        logger.info(f"✅ Получен контент через loadPageChunk: {len(content)} символов")
                                        return content
                        elif response.status_code == 401:
                            logger.debug("loadPageChunk требует авторизацию (token_v2 cookie)")
                            continue  # Переходим к следующему варианту заголовков
                        elif response.status_code == 400:
                            logger.debug(f"loadPageChunk вернул 400: {response.text[:200]}")
                    except Exception as variant_error:
                        logger.debug(f"Ошибка с вариантом заголовков: {variant_error}")
                        continue
            except Exception as e:
                logger.debug(f"loadPageChunk API: {e}")
            
            # Метод 3: Веб-скрапинг HTML (может содержать данные в JSON)
            try:
                logger.debug("Пробуем веб-скрапинг HTML...")
                page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
                web_headers = {
                    **self.headers,
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
                
                response = await client.get(page_url, headers=web_headers)
                if response.status_code == 200:
                    html = response.text
                    
                    # Используем BeautifulSoup для парсинга
                    try:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html, 'html.parser')
                        
                        # Убираем script и style
                        for script in soup(["script", "style", "noscript"]):
                            script.decompose()
                        
                        # Извлекаем текст из body
                        body = soup.find('body')
                        if body:
                            body_text = body.get_text(separator=' ', strip=True)
                            if body_text and len(body_text) > 200:
                                # Ищем summary/transcript в тексте
                                import re
                                summary_match = re.search(r'(?:summary|Summary|резюме|Резюме)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-()]{300,5000})', body_text, re.IGNORECASE)
                                transcript_match = re.search(r'(?:transcript|Transcript|транскрипт|Транскрипт)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-()]{500,10000})', body_text, re.IGNORECASE)
                                
                                content_parts = []
                                if summary_match:
                                    summary_text = summary_match.group(1).strip()
                                    summary_text = re.sub(r'\s+', ' ', summary_text)
                                    if len(summary_text) > 200:
                                        content_parts.append(f"## Summary\n{summary_text}")
                                
                                if transcript_match:
                                    transcript_text = transcript_match.group(1).strip()
                                    transcript_text = re.sub(r'\s+', ' ', transcript_text)
                                    if len(transcript_text) > 500:
                                        content_parts.append(f"## Transcript\n{transcript_text}")
                                
                                if content_parts:
                                    content = "\n\n".join(content_parts)
                                    if len(content.strip()) >= 100:
                                        logger.info(f"✅ Получен контент через веб-скрапинг HTML: {len(content)} символов")
                                        return content
                    except ImportError:
                        logger.debug("BeautifulSoup не установлен")
                    except Exception as bs_error:
                        logger.debug(f"Ошибка BeautifulSoup: {bs_error}")
            except Exception as e:
                logger.debug(f"Веб-скрапинг HTML: {e}")
        
        return None
