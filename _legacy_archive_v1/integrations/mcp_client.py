"""
Клиент для подключения к MCP Notion серверу.
Использует Python MCP SDK для получения контента страниц с AI meeting-notes блоками.
"""
import asyncio
import os
from typing import Dict, Any, Optional
from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from core.config import get_settings

# Пробуем импортировать различные транспорты для MCP
SSE_AVAILABLE = False
STREAMABLE_HTTP_AVAILABLE = False

try:
    from mcp.client.sse import sse_client
    SSE_AVAILABLE = True
except ImportError:
    logger.debug("SSE клиент недоступен")

try:
    from mcp.client.streamable_http import streamablehttp_client
    STREAMABLE_HTTP_AVAILABLE = True
except ImportError:
    logger.debug("streamable HTTP клиент недоступен")
    logger.debug("streamable HTTP клиент недоступен")


class MCPNotionClient:
    """Клиент для подключения к MCP Notion серверу."""
    
    async def fetch_page_via_remote_mcp(
        self, page_id: str, timeout: int = 60
    ) -> Optional[Dict[str, Any]]:
        """
        Пробует подключиться к remote MCP серверу Notion через notion-fetch.
        Это единственный способ получить transcription блоки программно.
        
        Args:
            page_id: ID страницы Notion
            timeout: Таймаут в секундах
            
        Returns:
            Словарь с данными страницы или None при ошибке
        """
        # Если MCP уже настроен в Cursor, он должен работать без дополнительной авторизации
        # Cursor уже авторизован, поэтому пробуем подключиться без заголовков авторизации
        
        # Вариант 1: SSE для подключения к remote MCP через Cursor
        # Это единственный способ получить transcription блоки программно
        # Если MCP уже настроен в Cursor, он должен работать без дополнительной авторизации
        if SSE_AVAILABLE:
            try:
                logger.info("🔍 Подключение к remote MCP Notion через SSE (без авторизации, т.к. Cursor уже авторизован)...")
                # Пробуем разные URL для remote MCP
                sse_urls = [
                    "https://mcp.notion.com/sse",
                    "https://mcp.notion.com",
                ]
                
                # Сначала пробуем без авторизации (Cursor уже авторизован)
                auth_variants_with_none = [None]
                
                for sse_url in sse_urls:
                    for auth_headers in auth_variants_with_none:
                        try:
                            logger.debug(f"Пробуем SSE URL: {sse_url}, авторизация: {list(auth_headers.keys()) if auth_headers else 'None'}")
                            async with sse_client(sse_url, timeout=timeout, headers=auth_headers if auth_headers else None) as (read, write):
                                async with ClientSession(read, write) as session:
                                    await asyncio.wait_for(
                                        session.initialize(),
                                        timeout=timeout
                                    )
                                    
                                    tools = await asyncio.wait_for(
                                        session.list_tools(),
                                        timeout=timeout
                                    )
                                    logger.info(f"✅ SSE MCP подключен, доступно {len(tools.tools)} инструментов")
                                    logger.debug(f"SSE MCP инструменты: {[t.name for t in tools.tools]}")
                                    
                                    # Ищем notion-fetch (единственный способ получить transcription)
                                    notion_fetch_found = False
                                    for tool in tools.tools:
                                        if tool.name == "notion-fetch":
                                            notion_fetch_found = True
                                            logger.info("✅ Найден notion-fetch - получаем meeting-notes...")
                                            
                                            # Пробуем разные варианты аргументов
                                            # Согласно документации, notion-fetch принимает параметр "url" (полный URL страницы)
                                            # Убираем query параметры и hash из URL
                                            import re
                                            # Формируем чистый URL без query параметров и hash
                                            clean_page_id = page_id.replace('-', '')
                                            # Пробуем разные форматы URL
                                            args_variants = [
                                                {"url": f"https://www.notion.so/{clean_page_id}"},
                                                {"url": f"https://www.notion.so/{page_id}"},
                                                {"url": f"https://notion.so/{clean_page_id}"},
                                                {"url": f"https://notion.so/{page_id}"},
                                            ]
                                            
                                            for args in args_variants:
                                                try:
                                                    logger.debug(f"Пробуем notion-fetch с аргументами: {list(args.keys())}")
                                                    result = await asyncio.wait_for(
                                                        session.call_tool("notion-fetch", arguments=args),
                                                        timeout=timeout
                                                    )
                                                    text_content = self._extract_text_from_result(result)
                                                    if text_content and len(text_content.strip()) >= 100:
                                                        logger.info(f"✅ SSE MCP: Получен контент ({len(text_content)} символов)")
                                                        return {"text": text_content}
                                                except Exception as arg_error:
                                                    logger.debug(f"Ошибка с аргументами {args}: {arg_error}")
                                                    continue
                                            
                                            break
                                    
                                    if not notion_fetch_found:
                                        logger.warning(f"notion-fetch не найден. Доступные инструменты: {[t.name for t in tools.tools]}")
                                    
                                    # Если успешно подключились, выходим из цикла вариантов авторизации
                                    break
                        except Exception as auth_error:
                            logger.debug(f"Вариант авторизации SSE не сработал: {auth_error}")
                            continue
            except Exception as e:
                logger.debug(f"SSE MCP недоступен: {e}")
        
        # Вариант 2: Streamable HTTP (без авторизации, т.к. Cursor уже авторизован)
        if STREAMABLE_HTTP_AVAILABLE:
            try:
                logger.info("Попытка подключения к remote MCP серверу Notion через HTTP (без авторизации)...")
                url = "https://mcp.notion.com/mcp"
                
                # Пробуем без авторизации (Cursor уже авторизован)
                headers = None
                
                async with streamablehttp_client(url, timeout=timeout, headers=headers) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await asyncio.wait_for(
                            session.initialize(),
                            timeout=timeout
                        )
                        
                        tools = await asyncio.wait_for(
                            session.list_tools(),
                            timeout=timeout
                        )
                        logger.debug(f"HTTP MCP инструменты: {[t.name for t in tools.tools]}")
                        
                        # Ищем notion-fetch
                        for tool in tools.tools:
                            if tool.name == "notion-fetch":
                                logger.info("Найден notion-fetch в HTTP MCP сервере")
                                
                                # Пробуем с URL страницы (чистый URL без query параметров и hash)
                                clean_page_id = page_id.replace('-', '')
                                page_url = f"https://www.notion.so/{clean_page_id}"
                                try:
                                    result = await asyncio.wait_for(
                                        session.call_tool(
                                            "notion-fetch",
                                            arguments={"url": page_url}
                                        ),
                                        timeout=timeout
                                    )
                                    text_content = self._extract_text_from_result(result)
                                    if text_content:
                                        logger.info(f"✅ HTTP MCP: Получен контент ({len(text_content)} символов)")
                                        return {"text": text_content}
                                except Exception as url_error:
                                    logger.debug(f"Ошибка с URL, пробуем с ID: {url_error}")
                                    
                                    # Пробуем с ID
                                    try:
                                        result = await asyncio.wait_for(
                                            session.call_tool(
                                                "notion-fetch",
                                                arguments={"id": page_id}
                                            ),
                                            timeout=timeout
                                        )
                                        text_content = self._extract_text_from_result(result)
                                        if text_content:
                                            logger.info(f"✅ HTTP MCP: Получен контент ({len(text_content)} символов)")
                                            return {"text": text_content}
                                    except Exception as id_error:
                                        logger.debug(f"Ошибка с ID: {id_error}")
                                
                                break
                        else:
                            logger.warning("notion-fetch не найден в HTTP MCP сервере")
                        
            except Exception as e:
                logger.debug(f"HTTP MCP недоступен (требуется OAuth): {e}")
        
        return None
    
    async def fetch_page(self, page_id: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
        """
        Получает контент страницы через MCP Notion.
        
        Args:
            page_id: ID страницы Notion
            timeout: Таймаут в секундах для подключения
            
        Returns:
            Словарь с данными страницы или None при ошибке
        """
        settings = get_settings()
        notion_token = settings.notion_token
        
        if not notion_token:
            logger.error("NOTION_TOKEN не установлен")
            return None
        
        # Используем только remote MCP сервер (уже настроен в Cursor)
        # Локальный сервер не имеет notion-fetch, поэтому не используем его
        result = await self.fetch_page_via_remote_mcp(page_id, timeout)
        if result:
            return result
        
        logger.warning(
            "Не удалось подключиться к remote MCP серверу Notion. "
            "Убедитесь, что MCP Notion настроен и активен в Cursor (Settings > Features > MCP)."
        )
        return None
    
    def _extract_text_from_result(self, result) -> str:
        """Извлекает текст из результата MCP инструмента."""
        text_content = ""
        if hasattr(result, 'content'):
            for content_item in result.content:
                if hasattr(content_item, 'text'):
                    text_content += content_item.text
                elif isinstance(content_item, dict):
                    if 'text' in content_item:
                        text_content += content_item['text']
                    elif 'type' in content_item and content_item['type'] == 'text':
                        text_content += content_item.get('text', '')
        return text_content
    
    async def _fetch_blocks_recursive(
        self, 
        session: ClientSession, 
        block_id: str, 
        timeout: int,
        depth: int = 0,
        max_depth: int = 10
    ) -> str:
        """
        Рекурсивно получает все блоки страницы через API-get-block-children.
        Пропускает transcription блоки (они не поддерживаются через API).
        
        Args:
            session: MCP сессия
            block_id: ID блока (страницы)
            timeout: Таймаут для запросов
            depth: Текущая глубина рекурсии
            max_depth: Максимальная глубина рекурсии
            
        Returns:
            Текст контента страницы
        """
        if depth > max_depth:
            return ""
        
        try:
            # Получаем дочерние блоки
            try:
                result = await asyncio.wait_for(
                    session.call_tool(
                        "API-get-block-children",
                        arguments={"block_id": block_id}
                    ),
                    timeout=timeout
                )
            except Exception as e:
                # Если это ошибка для transcription блока, пропускаем его
                error_str = str(e).lower()
                if "transcription" in error_str or "not supported" in error_str or "validation_error" in error_str:
                    logger.debug(f"Пропускаем transcription блок {block_id} в MCP")
                    return ""
                raise
            
            # Извлекаем JSON из результата
            result_text = self._extract_text_from_result(result)
            if not result_text:
                return ""
            
            # Парсим JSON ответ
            import json
            try:
                data = json.loads(result_text)
            except json.JSONDecodeError:
                # Если это не JSON, возвращаем как есть
                return result_text
            
            # Извлекаем блоки из ответа
            blocks = data.get("results", [])
            if not blocks:
                return ""
            
            content_parts = []
            for block in blocks:
                block_type = block.get("type", "unknown")
                block_id = block.get("id", "")
                
                # Извлекаем текст из блока в зависимости от типа
                block_text = self._extract_text_from_block(block)
                if block_text:
                    content_parts.append(block_text)
                
                # Если у блока есть дети, рекурсивно получаем их
                has_children = block.get("has_children", False)
                if has_children and block_id:
                    try:
                        child_text = await self._fetch_blocks_recursive(
                            session, block_id, timeout, depth + 1, max_depth
                        )
                        if child_text:
                            content_parts.append(child_text)
                    except Exception as child_error:
                        # Пропускаем transcription блоки
                        error_str = str(child_error).lower()
                        if "transcription" in error_str or "not supported" in error_str or "validation_error" in error_str:
                            logger.debug(f"Пропускаем transcription блок {block_id} в MCP рекурсии")
                        else:
                            logger.debug(f"Ошибка при получении детей блока {block_id}: {child_error}")
            
            return "\n".join(content_parts)
            
        except Exception as e:
            # Если это ошибка для transcription блока, возвращаем пустую строку
            error_str = str(e).lower()
            if "transcription" in error_str or "not supported" in error_str or "validation_error" in error_str:
                logger.debug(f"Пропускаем transcription блок {block_id} в MCP")
                return ""
            logger.debug(f"Ошибка при получении блоков {block_id}: {e}")
            return ""
    
    def _extract_text_from_block(self, block: Dict[str, Any]) -> str:
        """Извлекает текст из блока Notion."""
        block_type = block.get("type", "unknown")
        
        # Для разных типов блоков извлекаем текст по-разному
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", 
                         "bulleted_list_item", "numbered_list_item", "to_do", 
                         "quote", "callout"]:
            rich_text = block.get(block_type, {}).get("rich_text", [])
            text = "".join([rt.get("plain_text", "") for rt in rich_text])
            
            # Добавляем форматирование для заголовков
            if block_type.startswith("heading"):
                level = block_type.split("_")[1]
                text = f"{'#' * int(level)} {text}"
            elif block_type == "to_do":
                checked = block.get(block_type, {}).get("checked", False)
                checkbox = " [x] " if checked else " [ ] "
                text = f"{checkbox}{text}"
            elif block_type == "bulleted_list_item":
                text = f"• {text}"
            elif block_type == "numbered_list_item":
                text = f"1. {text}"
            
            return text
        
        # Для unsupported блоков (включая meeting-notes) возвращаем тип
        elif block_type == "unsupported":
            return f"[Unsupported block: {block.get('unsupported', {}).get('type', 'unknown')}]"
        
        return ""
