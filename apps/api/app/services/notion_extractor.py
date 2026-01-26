import asyncio
import json
import re
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from loguru import logger
from notion_client import AsyncClient
from playwright.async_api import async_playwright

from app.config import get_settings

class NotionExtractor:
    """
    Усовершенствованный сервис извлечения данных (Strategy A & B).
    Имитирует логику MCP-сервера для работы с AI Meeting Notes.
    """
    
    def __init__(self):
        settings = get_settings()
        self.notion = AsyncClient(auth=settings.notion_token)
        # Путь к данным для сессии
        self.auth_file = Path(__file__).parent.parent.parent / "data" / "notion_auth.json"
        
    async def get_all_blocks_recursive(self, block_id: str, all_blocks: List[Dict] = None) -> List[Dict]:
        """Рекурсивное получение всех блоков, включая вложенные в 'unsupported'."""
        if all_blocks is None:
            all_blocks = []
            
        try:
            response = await self.notion.blocks.children.list(block_id=block_id, page_size=100)
            
            for block in response.get("results", []):
                all_blocks.append(block)
                # Даже если блок обычный, заходим вглубь
                if block.get("has_children"):
                    await self.get_all_blocks_recursive(block["id"], all_blocks)
            
            # Пагинация
            cursor = response.get("next_cursor")
            while response.get("has_more") and cursor:
                response = await self.notion.blocks.children.list(
                    block_id=block_id, 
                    page_size=100, 
                    start_cursor=cursor
                )
                for block in response.get("results", []):
                    all_blocks.append(block)
                    if block.get("has_children"):
                        await self.get_all_blocks_recursive(block["id"], all_blocks)
                cursor = response.get("next_cursor")
                
            return all_blocks
        except Exception as e:
            logger.error(f"Ошибка API при обходе дерева блоков: {e}")
            return all_blocks

    def deep_extract_text(self, obj: Any) -> List[str]:
        """
        Рекурсивный поиск ЛЮБОГО текста (Strategy A 'Refinement').
        Ищет ключи 'plain_text', 'content', 'title' в любых объектах.
        Это позволяет вытащить данные из скрытых свойств AI-блоков.
        """
        texts = []
        if isinstance(obj, dict):
            # Приоритетные поля для Notion
            for key in ["plain_text", "content", "title"]:
                if key in obj and isinstance(obj[key], str):
                    texts.append(obj[key])
            
            # Заходим глубже
            for value in obj.values():
                texts.extend(self.deep_extract_text(value))
        elif isinstance(obj, list):
            for item in obj:
                texts.extend(self.deep_extract_text(item))
        return texts

    def format_block_as_markdown(self, block: Dict) -> str:
        """Имитация логики MCP fetch для преобразования блока в Markdown."""
        block_type = block.get("type", "unknown")
        
        # Вытаскиваем весь доступный текст через глубокий поиск
        # Это ключевое уточнение из отчета для работы с 'unsupported'
        all_text = self.deep_extract_text(block.get(block_type, {}))
        text_content = " ".join(all_text).strip()
        
        if not text_content and block_type == "unsupported":
            # Если блок unsupported, пробуем найти текст во всем объекте блока
            text_content = " ".join(self.deep_extract_text(block)).strip()

        if not text_content:
            return ""

        # Простая разметка для структуры
        if block_type.startswith("heading_"):
            level = block_type.split("_")[1]
            return f"{'#' * int(level)} {text_content}"
        elif block_type == "bulleted_list_item":
            return f"* {text_content}"
        elif block_type == "numbered_list_item":
            return f"1. {text_content}"
        elif block_type == "to_do":
            checked = "[x]" if block.get("to_do", {}).get("checked") else "[ ]"
            return f"{checked} {text_content}"
        elif block_type == "quote":
            return f"> {text_content}"
        
        return text_content

    async def extract_via_api(self, page_id: str) -> Dict[str, Any]:
        """Стратегия A: Продвинутое извлечение через API (MCP Logic)."""
        logger.info(f"🔌 Имитация MCP fetch для страницы {page_id}")
        
        blocks = await self.get_all_blocks_recursive(page_id)
        if not blocks:
            return {"success": False, "error": "Не удалось получить дерево блоков"}
            
        md_parts = []
        for block in blocks:
            line = self.format_block_as_markdown(block)
            if line:
                md_parts.append(line)
                    
        full_markdown = "\n\n".join(md_parts)
        
        # Ищем именно саммари (как указано в уточнениях)
        # Блоки AI обычно содержат заголовки типа 'Summary'
        summary_match = re.search(r"(?:AI Summary|Summary|Саммари|Резюме)[\s\S]*?(?=\n\n#|$)", full_markdown, re.I)
        
        if summary_match:
            return {"success": True, "content": summary_match.group(0).strip()}
        
        # Если нашли много текста, но без явного заголовка
        if len(full_markdown) > 200:
            return {"success": True, "content": full_markdown}
            
        return {"success": False, "error": "Данные AI Meeting Notes не найдены в JSON-структуре API"}

    async def extract_via_playwright(self, page_id: str) -> Dict[str, Any]:
        """Стратегия B: Фоновый парсер (Headless Browser) с Replay Session."""
        logger.info(f"🌐 Запуск Strategy B (Playwright) для {page_id}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            # Настройка контекста (Session Replay)
            context_options = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            if self.auth_file.exists():
                logger.info(f"📁 Загрузка сессии: {self.auth_file}")
                context_options["storage_state"] = str(self.auth_file)
            else:
                auth_json = os.environ.get("NOTION_AUTH_JSON")
                if auth_json:
                    temp_auth = Path("/tmp/notion_auth.json")
                    temp_auth.write_text(auth_json)
                    context_options["storage_state"] = str(temp_auth)
                else:
                    await browser.close()
                    return {"success": False, "error": "Отсутствует auth.json для Strategy B"}

            context = await browser.new_context(**context_options)
            page = await context.new_page()
            
            # Формируем URL без дефисов
            clean_id = page_id.replace("-", "")
            url = f"https://www.notion.so/{clean_id}"
            
            try:
                # Переход с ожиданием networkidle (как просили в инструкции)
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Smart Scroll для обхода виртуализации (Lazy Loading)
                logger.info("📜 Smart Scroll в процессе...")
                for i in range(15):
                    # Прокрутка по 800px (как в инструкции)
                    await page.evaluate("window.scrollBy(0, 800)")
                    await asyncio.sleep(0.6)
                    # Проверяем, не появился ли уже нужный блок
                    if i > 5:
                        has_summary = await page.get_by_text(re.compile(r"Summary|Саммари", re.I)).count() > 0
                        if has_summary: break
                
                await asyncio.sleep(3) # Финальное ожидание рендеринга
                
                # Извлекаем текст через надежные селекторы
                # 1. Сначала пробуем найти именно блоки с AI Summary
                summary_element = page.locator("div[data-block-id]").filter(has_text=re.compile(r"Summary|Саммари", re.I)).first()
                
                content = None
                if await summary_element.count() > 0:
                    # Пытаемся взять весь родительский контейнер контента
                    content = await summary_element.locator("xpath=./ancestor::div[contains(@class, 'notion-page-content')]").inner_text()
                
                if not content:
                    # Если не вышло, берем все блоки данных
                    all_blocks = await page.locator("div[data-block-id]").all_inner_texts()
                    content = "\n\n".join(all_blocks)
                
                await browser.close()
                
                if content and len(content.strip()) > 50:
                    return {"success": True, "content": content.strip()}
                return {"success": False, "error": "Браузер открыл страницу, но контент пуст"}
                
            except Exception as e:
                await browser.close()
                return {"success": False, "error": f"Ошибка в Strategy B: {str(e)}"}

    async def extract_data(self, page_id: str) -> Dict[str, Any]:
        """Главный гибридный метод."""
        # Метод 1 (API/MCP Refinement)
        result = await self.extract_via_api(page_id)
        if result["success"]:
            result["method"] = "api_mcp"
            return result
            
        # Метод 2 (Playwright Replay Session)
        logger.warning("Strategy A не дала результатов, включаем Strategy B...")
        result = await self.extract_via_playwright(page_id)
        if result["success"]:
            result["method"] = "playwright_headless"
            
        return result

# Singleton
notion_extractor = NotionExtractor()
