"""
Парсер HTML страниц Notion для извлечения meeting-notes данных.
Notion встраивает данные в HTML страницы, которые можно извлечь.
"""
import httpx
import re
import json
from typing import Dict, Any, Optional
from loguru import logger
from core.config import get_settings


class NotionHTMLParser:
    """Парсер HTML страниц Notion для извлечения meeting-notes."""
    
    def __init__(self):
        settings = get_settings()
        self.token = settings.notion_mcp_token or settings.notion_token
        if not self.token:
            raise ValueError("NOTION_TOKEN или NOTION_MCP_TOKEN не установлен")
    
    async def fetch_page_html(self, page_id: str) -> Optional[str]:
        """
        Получает HTML страницы Notion.
        
        Args:
            page_id: ID страницы Notion
            
        Returns:
            HTML контент страницы или None
        """
        page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": "2025-09-03",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9"
            }
            
            try:
                response = await client.get(page_url, headers=headers)
                response.raise_for_status()
                return response.text
            except Exception as e:
                logger.debug(f"Ошибка при получении HTML: {e}")
                return None
    
    def extract_meeting_notes_from_html(self, html_content: str) -> Optional[Dict[str, Any]]:
        """
        Извлекает meeting-notes данные из HTML страницы Notion.
        
        Notion встраивает данные в:
        1. JSON в <script> тегах (window.__INITIAL_STATE__, notion-page-data и т.д.)
        2. data-notion-page-id атрибуты
        3. Прямой текст в HTML
        
        Returns:
            Словарь с данными meeting-notes или None
        """
        if not html_content:
            return None
        
        # Метод 1: Ищем JSON данные в script тегах (более специфичные паттерны для Notion)
        json_patterns = [
            r'<script[^>]*id="notion-app-data"[^>]*>(.*?)</script>',
            r'<script[^>]*type="application/json"[^>]*data-page-id[^>]*>(.*?)</script>',
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
            r'notion-page-data\s*=\s*({.*?});',
        ]
        
        for pattern in json_patterns:
            matches = re.finditer(pattern, html_content, re.DOTALL)
            for match in matches:
                try:
                    json_str = match.group(1).strip()
                    # Убираем возможные комментарии и лишние символы
                    json_str = re.sub(r'//.*?\n', '\n', json_str)
                    
                    data = json.loads(json_str)
                    
                    # Ищем meeting-notes данные в JSON
                    meeting_data = self._find_meeting_notes_in_json(data)
                    if meeting_data:
                        logger.info("✅ Найдены meeting-notes данные в JSON")
                        return meeting_data
                except (json.JSONDecodeError, Exception) as e:
                    logger.debug(f"Ошибка парсинга JSON: {e}")
                    continue
        
        # Метод 2: Ищем meeting-notes в тексте HTML
        meeting_patterns = [
            r'<meeting-notes[^>]*>(.*?)</meeting-notes>',
            r'meeting-notes["\']?\s*:\s*({.*?})',
            r'transcript["\']?\s*:\s*["\'](.*?)["\']',
            r'summary["\']?\s*:\s*["\'](.*?)["\']',
        ]
        
        for pattern in meeting_patterns:
            matches = re.finditer(pattern, html_content, re.DOTALL | re.IGNORECASE)
            for match in matches:
                content = match.group(1)
                if content and len(content.strip()) > 50:
                    logger.info(f"✅ Найдены meeting-notes данные в HTML (паттерн: {pattern[:30]}...)")
                    return {"content": content, "source": "html_pattern"}
        
        # Метод 3: Ищем упоминания meeting/transcript в тексте и извлекаем окружающий контекст
        if "meeting" in html_content.lower() or "transcript" in html_content.lower() or "summary" in html_content.lower():
            logger.info("Найдены упоминания meeting/transcript/summary, пробуем извлечь контекст...")
            
            # Ищем более структурированные паттерны в текстовом контенте (не в script тегах)
            # Сначала удаляем все script и style теги
            text_only_html = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
            text_only_html = re.sub(r'<style[^>]*>.*?</style>', '', text_only_html, flags=re.DOTALL | re.IGNORECASE)
            
            structured_patterns = [
                # Паттерн для summary (ищем в текстовом контенте)
                r'(?:summary|Summary|SUMMARY)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-]{200,5000})',
                # Паттерн для transcript
                r'(?:transcript|Transcript|TRANSCRIPT)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-]{200,10000})',
                # Паттерн для meeting notes
                r'(?:meeting\s+notes?|Meeting\s+Notes?)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-]{200,5000})',
            ]
            
            all_contexts = []
            for pattern in structured_patterns:
                matches = re.finditer(pattern, text_only_html, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    context = match.group(1)
                    # Очищаем от HTML тегов и лишних символов
                    context = re.sub(r'<[^>]+>', ' ', context)
                    context = re.sub(r'[{}"]+', ' ', context)
                    context = re.sub(r'\s+', ' ', context).strip()
                    
                    # Пропускаем JavaScript код
                    if any(js_keyword in context for js_keyword in ['function', 'var ', 'const ', 'let ', 'window.', 'document.']):
                        continue
                    
                    # Проверяем, что это текст (содержит слова)
                    words = context.split()
                    if len(context) > 200 and len(words) > 20:
                        all_contexts.append(context)
            
            # Если нашли структурированные данные, используем их
            if all_contexts:
                # Объединяем все контексты
                content = "\n\n".join(all_contexts)
                logger.info(f"✅ Извлечен структурированный контекст из HTML: {len(content)} символов")
                return {"content": content, "source": "html_structured"}
            
            # Fallback: ищем любой контекст вокруг упоминаний, но исключаем JavaScript
            context_pattern = r'(?:meeting|transcript|summary)[^<]*?([^<]{200,5000})'
            matches = re.finditer(context_pattern, html_content, re.IGNORECASE | re.DOTALL)
            contexts = []
            for match in matches:
                context = match.group(1)
                
                # Пропускаем JavaScript код
                if any(js_keyword in context for js_keyword in ['function', 'var ', 'const ', 'let ', 'window.', 'document.', 'fetch(', 'JSON.stringify']):
                    continue
                
                # Очищаем от HTML тегов
                context = re.sub(r'<[^>]+>', ' ', context)
                context = re.sub(r'\s+', ' ', context).strip()
                
                # Проверяем, что это похоже на текст (содержит слова, не только символы)
                words = context.split()
                if len(words) > 20:  # Минимум 20 слов
                    contexts.append(context)
            
            if contexts:
                # Берем последний контекст (самая свежая встреча)
                content = contexts[-1]
                logger.info(f"✅ Извлечен контекст из HTML: {len(content)} символов")
                return {"content": content, "source": "html_context"}
        
        return None
    
    def _find_meeting_notes_in_json(self, data: Any, depth: int = 0) -> Optional[Dict[str, Any]]:
        """Рекурсивно ищет meeting-notes данные в JSON структуре."""
        if depth > 15:  # Увеличиваем глубину для более глубокого поиска
            return None
        
        if isinstance(data, dict):
            # Ищем ключи, связанные с meeting-notes
            for key, value in data.items():
                key_lower = key.lower() if isinstance(key, str) else ""
                
                # Ищем ключи, связанные с meeting-notes, transcript, summary
                if any(keyword in key_lower for keyword in ["meeting", "transcript", "summary", "notes"]):
                    if isinstance(value, str) and len(value) > 100:
                        return {"key": key, "value": value, "source": "json"}
                    elif isinstance(value, dict):
                        # Если значение - словарь, ищем в нем текст
                        text_parts = []
                        for sub_key, sub_value in value.items():
                            if isinstance(sub_value, str) and len(sub_value) > 50:
                                text_parts.append(sub_value)
                        if text_parts:
                            return {"key": key, "value": "\n\n".join(text_parts), "source": "json"}
                    elif isinstance(value, list):
                        # Если значение - список, ищем строки
                        text_parts = [str(item) for item in value if isinstance(item, str) and len(item) > 50]
                        if text_parts:
                            return {"key": key, "value": "\n\n".join(text_parts), "source": "json"}
                
                # Рекурсивный поиск
                result = self._find_meeting_notes_in_json(value, depth + 1)
                if result:
                    return result
        
        elif isinstance(data, list):
            for item in data:
                result = self._find_meeting_notes_in_json(item, depth + 1)
                if result:
                    return result
        
        return None
    
    async def get_meeting_content(self, page_id: str) -> Optional[str]:
        """
        Получает контент meeting-notes из HTML страницы.
        
        Returns:
            Текст контента или None
        """
        html_content = await self.fetch_page_html(page_id)
        if not html_content:
            return None
        
        meeting_data = self.extract_meeting_notes_from_html(html_content)
        if not meeting_data:
            return None
        
        # Извлекаем текст из данных
        content = meeting_data.get("content") or meeting_data.get("value")
        
        if isinstance(content, str):
            return content
        elif isinstance(content, dict):
            # Пробуем извлечь текст из словаря
            text_parts = []
            for key in ["summary", "transcript", "notes", "text", "content"]:
                if key in content:
                    text_parts.append(str(content[key]))
            return "\n\n".join(text_parts) if text_parts else None
        elif isinstance(content, list):
            return "\n\n".join([str(item) for item in content])
        
        return None
