"""
Сервис для работы с локальным MCP Notion Server.
Запускает @notionhq/notion-mcp-server локально и использует протокол MCP для получения данных.
"""
import asyncio
import subprocess
import os
import socket
import httpx
import threading
import shlex
import json
from typing import Optional, Dict, Any
from loguru import logger
from pathlib import Path

from app.config import get_settings


class NotionMCPService:
    """Сервис для работы с локальным MCP Notion Server."""
    
    def __init__(self):
        settings = get_settings()
        self.token = settings.notion_token
        if not self.token:
            raise ValueError("NOTION_TOKEN не установлен")
        
        self.port = 3002  # Начинаем с 3002, так как 3001 обычно занят Next.js
        self.auth_token = "local_mcp_auth_token_12345"
        self.server_process = None
        self.server_url = f"http://127.0.0.1:{self.port}"
        self.initialized = False
        self.session_id = None
        self.log_threads = []  # Потоки для чтения логов
    
    def _read_output(self, pipe, log_func, prefix: str):
        """Читает вывод процесса и логирует его в фоне."""
        try:
            for line in iter(pipe.readline, b''):
                if line:
                    decoded = line.decode('utf-8', errors='ignore').strip()
                    if decoded:
                        log_func(f"[{prefix}] {decoded}")
        except Exception as e:
            logger.debug(f"Ошибка чтения {prefix}: {e}")
        finally:
            pipe.close()
    
    def _parse_mcp_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Парсит ответ от MCP сервера (JSON или SSE)."""
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            # Parse SSE
            for line in response.text.splitlines():
                if line.startswith("data: "):
                    try:
                        return json.loads(line[6:])
                    except json.JSONDecodeError:
                        pass
            raise ValueError("No valid JSON data in SSE response")
        return response.json()

    async def _check_server_running(self) -> bool:
        """Проверяет, запущен ли MCP сервер на порту."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                # Пробуем initialize запрос
                init_request = {
                    "jsonrpc": "2.0",
                    "id": 0,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "notion-mcp-client",
                            "version": "1.0.0"
                        }
                    }
                }
                headers = {
                    "Authorization": f"Bearer {self.auth_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": "2024-11-05"
                }
                response = await client.post(
                    f"{self.server_url}/mcp",
                    headers=headers,
                    json=init_request
                )
                if response.status_code == 200:
                    try:
                        data = self._parse_mcp_response(response)
                        if "result" in data:
                            logger.info(f"✅ MCP сервер уже запущен на порту {self.port}")
                            result = data["result"]
                            if isinstance(result, dict) and "sessionId" in result:
                                self.session_id = result["sessionId"]
                            # Также проверяем заголовки ответа
                            if "mcp-session-id" in response.headers:
                                self.session_id = response.headers["mcp-session-id"]
                            self.initialized = True
                            return True
                        elif "error" in data:
                            # Если это MCP ошибка (не JSON parse error), значит это MCP сервер
                            error_code = data.get("error", {}).get("code") if isinstance(data.get("error"), dict) else None
                            if error_code is not None:  # MCP ошибки имеют код
                                logger.debug(f"MCP сервер на порту {self.port} вернул ошибку: {data['error']}")
                                # Это MCP сервер, но он не инициализирован - попробуем инициализировать
                                return False
                    except (ValueError, KeyError) as json_error:
                        # Не JSON ответ - это не MCP сервер
                        logger.debug(f"Сервер на порту {self.port} вернул не JSON ответ (не MCP): {json_error}")
                        return False
        except httpx.HTTPStatusError as e:
            # HTTP ошибка - возможно это не MCP сервер
            logger.debug(f"HTTP ошибка при проверке порта {self.port}: {e.response.status_code}")
            return False
        except Exception as e:
            logger.debug(f"Сервер на порту {self.port} не отвечает: {e}")
        return False
    
    async def start_server(self) -> bool:
        """Запускает локальный MCP Notion сервер."""
        try:
            # Проверяем, не запущен ли уже сервер
            if await self._check_server_running():
                return True
            
            # Проверяем, занят ли порт
            port_available = False
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind(('0.0.0.0', self.port))
                sock.close()
                port_available = True
            except OSError:
                # Порт занят - проверяем, может это уже наш MCP сервер
                logger.info(f"Порт {self.port} занят. Проверяем, не MCP ли это сервер...")
                await asyncio.sleep(1)
                if await self._check_server_running():
                    return True
                # Если не MCP сервер, ищем свободный порт
                port_available = False
            
            if not port_available:
                # Ищем свободный порт (начинаем с 3002, так как 3001 обычно занят Next.js)
                for alt_port in range(3002, 3010):
                    self.port = alt_port
                    self.server_url = f"http://127.0.0.1:{self.port}"
                    # Проверяем, может там уже работает MCP сервер
                    if await self._check_server_running():
                        logger.info(f"Используем существующий MCP сервер на порту {self.port}")
                        return True
                    # Проверяем, свободен ли порт
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        sock.bind(('0.0.0.0', self.port))
                        sock.close()
                        logger.info(f"Найден свободный порт: {self.port}")
                        break  # Нашли свободный порт
                    except OSError:
                        continue
                else:
                    logger.error("Не удалось найти свободный порт для MCP сервера (3001-3009 заняты)")
                    return False
            
            # Валидация токена перед запуском
            if not self.token or len(self.token) < 10:
                logger.error("NOTION_TOKEN не установлен или слишком короткий")
                return False
            
            if not self.token.startswith("secret_") and not self.token.startswith("ntn_"):
                logger.warning("NOTION_TOKEN не начинается с 'secret_' или 'ntn_', возможно неверный формат")
            
            # Согласно техническому отчету: критическая проверка версии Node.js
            # MCP SDK требует Node.js v18.0.0 или выше
            try:
                node_version_output = subprocess.run(
                    ["node", "-v"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True
                )
                node_version = node_version_output.stdout.strip()
                # Парсим версию (формат: v18.0.0)
                version_number = int(node_version.lstrip('v').split('.')[0])
                if version_number < 18:
                    logger.error(
                        f"❌ КРИТИЧЕСКАЯ ОШИБКА: Node.js версия {node_version} слишком старая!\n"
                        f"   MCP SDK требует Node.js v18.0.0 или выше (рекомендуется v20 LTS).\n"
                        f"   Установите актуальную версию Node.js: https://nodejs.org/"
                    )
                    return False
                logger.debug(f"✅ Node.js версия: {node_version} (совместима с MCP)")
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.error(
                    f"❌ КРИТИЧЕСКАЯ ОШИБКА: Node.js не найден или недоступен!\n"
                    f"   MCP SDK требует Node.js v18.0.0 или выше.\n"
                    f"   Установите Node.js: https://nodejs.org/\n"
                    f"   Ошибка: {e}"
                )
                return False
            
            logger.info(f"🚀 Запуск локального MCP Notion сервера на порту {self.port}...")
            
            # Запускаем сервер через npx с HTTP transport
            # Проверяем наличие Node.js и npx
            try:
                subprocess.run(["npx", "--version"], capture_output=True, timeout=5, check=True)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                logger.warning("npx не найден. Установите Node.js для использования локального MCP сервера.")
                return False
            
            # Обертываем команду в bash -c для правильной передачи NOTION_TOKEN
            # Экранируем токен для безопасности в shell команде
            safe_token = shlex.quote(self.token)
            safe_auth_token = shlex.quote(self.auth_token)
            
            command = f"NOTION_TOKEN={safe_token} npx -y @notionhq/notion-mcp-server --transport http --port {self.port} --auth-token {safe_auth_token}"
            
            # Запускаем сервер в фоне через bash -c
            self.server_process = subprocess.Popen(
                ["bash", "-c", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=Path(__file__).parent.parent.parent.parent,
                bufsize=1  # Line buffered
            )
            
            # Запускаем фоновые потоки для чтения логов
            stdout_thread = threading.Thread(
                target=self._read_output,
                args=(self.server_process.stdout, logger.info, "MCP stdout"),
                daemon=True
            )
            stderr_thread = threading.Thread(
                target=self._read_output,
                args=(self.server_process.stderr, logger.error, "MCP stderr"),
                daemon=True
            )
            stdout_thread.start()
            stderr_thread.start()
            self.log_threads = [stdout_thread, stderr_thread]
            
            # Ждем запуска сервера (проверяем через initialize)
            for attempt in range(15):  # Увеличиваем время ожидания до 15 секунд
                await asyncio.sleep(1)
                
                # Проверяем, не завершился ли процесс с ошибкой
                if self.server_process.poll() is not None:
                    # Процесс завершился - читаем ошибки (если потоки еще не прочитали)
                    try:
                        stdout, stderr = self.server_process.communicate(timeout=1)
                        if stderr:
                            logger.error(f"MCP stderr (после завершения): {stderr.decode('utf-8', errors='ignore')}")
                        if stdout:
                            logger.debug(f"MCP stdout (после завершения): {stdout.decode('utf-8', errors='ignore')}")
                    except subprocess.TimeoutExpired:
                        pass
                    logger.error(f"MCP сервер завершился с кодом {self.server_process.returncode}")
                    return False
                
                try:
                    if await self._check_server_running():
                        logger.info(f"✅ Локальный MCP сервер запущен на порту {self.port}")
                        return True
                except Exception as e:
                    if attempt == 0:
                        logger.debug(f"Ожидание запуска MCP сервера... (попытка {attempt + 1})")
                    continue
            
            # Проверяем, не завершился ли процесс с ошибкой (если еще не проверили в цикле)
            if self.server_process.poll() is not None:
                try:
                    stdout, stderr = self.server_process.communicate(timeout=1)
                    if stderr:
                        logger.error(f"MCP stderr (финальная проверка): {stderr.decode('utf-8', errors='ignore')}")
                    if stdout:
                        logger.debug(f"MCP stdout (финальная проверка): {stdout.decode('utf-8', errors='ignore')}")
                except subprocess.TimeoutExpired:
                    pass
                logger.error(f"MCP сервер завершился с кодом {self.server_process.returncode}")
                return False
            
            logger.warning("MCP сервер не запустился за 15 секунд")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка запуска локального MCP сервера: {e}")
            return False
    
    async def stop_server(self):
        """Останавливает локальный MCP сервер."""
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
                logger.info("MCP сервер остановлен")
            except Exception as e:
                logger.debug(f"Ошибка остановки сервера: {e}")
                if self.server_process:
                    self.server_process.kill()
    
    async def fetch_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        """
        Получает контент страницы через локальный MCP сервер используя протокол MCP.
        
        Args:
            page_id: ID страницы Notion
            
        Returns:
            Словарь с данными страницы или None
        """
        try:
            # Запускаем сервер, если еще не запущен
            if not await self.start_server():
                logger.warning("Не удалось запустить MCP сервер")
                return None
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {
                    "Authorization": f"Bearer {self.auth_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": "2024-11-05"
                }
                
                # Если еще не инициализированы, делаем initialize
                if not self.initialized:
                    init_request = {
                        "jsonrpc": "2.0",
                        "id": 0,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {
                                "name": "notion-mcp-client",
                                "version": "1.0.0"
                            }
                        }
                    }
                    init_response = await client.post(
                        f"{self.server_url}/mcp",
                        headers=headers,
                        json=init_request
                    )
                    if init_response.status_code == 200:
                        init_data = self._parse_mcp_response(init_response)
                        if "result" in init_data:
                            # Сохраняем session_id если есть
                            result = init_data["result"]
                            if isinstance(result, dict) and "sessionId" in result:
                                self.session_id = result["sessionId"]
                                headers["mcp-session-id"] = self.session_id
                            # Также проверяем заголовки ответа
                            if "mcp-session-id" in init_response.headers:
                                self.session_id = init_response.headers["mcp-session-id"]
                                headers["mcp-session-id"] = self.session_id
                            self.initialized = True
                            logger.info(f"MCP сервер инициализирован (session_id: {self.session_id})")
                        elif "error" in init_data:
                            logger.warning(f"MCP initialize вернул ошибку: {init_data['error']}")
                    else:
                        error_text = init_response.text[:200]
                        logger.warning(f"Не удалось инициализировать MCP сервер: {init_response.status_code} - {error_text}")
                
                # Получаем список доступных инструментов
                list_tools_request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list"
                }
                
                if self.session_id:
                    headers["mcp-session-id"] = self.session_id
                
                # Получаем список инструментов
                tools_response = await client.post(
                    f"{self.server_url}/mcp",
                    headers=headers,
                    json=list_tools_request
                )
                
                tool_name = "notion-fetch"  # Правильное имя согласно документации Notion MCP
                if tools_response.status_code == 200:
                    tools_data = self._parse_mcp_response(tools_response)
                    if "result" in tools_data and "tools" in tools_data["result"]:
                        available_tools = [t.get("name") for t in tools_data["result"]["tools"]]
                        logger.info(f"Доступные инструменты MCP: {available_tools}")
                        
                        # Ищем подходящий инструмент для получения страницы
                        # Согласно документации: notion-fetch (или fetch для OpenAI клиентов)
                        possible_names = [
                            "notion-fetch",
                            "fetch",  # Для OpenAI клиентов префикс убирается
                            "retrieve-a-page",
                            "fetch-page",
                            "get-page",
                            "fetch_page"
                        ]
                        for name in possible_names:
                            if name in available_tools:
                                tool_name = name
                                logger.info(f"Используем инструмент: {tool_name}")
                                break
                
                # Формируем MCP JSON-RPC запрос для получения страницы
                # Согласно документации, notion-fetch принимает URL страницы
                # Формат URL: https://notion.so/{page_id} или https://www.notion.so/{page_id}
                page_id_clean = page_id.replace('-', '')
                page_url = f"https://www.notion.so/{page_id_clean}"
                
                if self.session_id:
                    headers["mcp-session-id"] = self.session_id
                
                # Пробуем сначала с URL (предпочтительный способ согласно документации)
                mcp_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": {
                            "url": page_url
                        }
                    }
                }
                
                response = await client.post(
                    f"{self.server_url}/mcp",
                    headers=headers,
                    json=mcp_request
                )
                
                if response.status_code == 200:
                    data = self._parse_mcp_response(response)
                    if "result" in data:
                        result = data["result"]
                        logger.info(f"✅ Получены данные через MCP сервер (инструмент: {tool_name}, URL: {page_url})")
                        return result
                    elif "error" in data:
                        error_info = data["error"]
                        error_code = error_info.get("code") if isinstance(error_info, dict) else None
                        error_message = error_info.get("message", str(error_info)) if isinstance(error_info, dict) else str(error_info)
                        
                        # Если ошибка связана с форматом аргументов, пробуем fallback с page_id
                        if error_code in [-32602, -32603] or "url" in error_message.lower() or "invalid" in error_message.lower():
                            logger.debug(f"MCP вернул ошибку с URL, пробуем fallback с page_id: {error_message}")
                            
                            # Fallback: пробуем с page_id (для обратной совместимости)
                            fallback_request = {
                                "jsonrpc": "2.0",
                                "id": 3,
                                "method": "tools/call",
                                "params": {
                                    "name": tool_name,
                                    "arguments": {
                                        "page_id": page_id_clean
                                    }
                                }
                            }
                            
                            fallback_response = await client.post(
                                f"{self.server_url}/mcp",
                                headers=headers,
                                json=fallback_request
                            )
                            
                            if fallback_response.status_code == 200:
                                fallback_data = self._parse_mcp_response(fallback_response)
                                if "result" in fallback_data:
                                    logger.info(f"✅ Получены данные через MCP сервер (fallback с page_id: {page_id_clean})")
                                    return fallback_data["result"]
                                elif "error" in fallback_data:
                                    logger.error(f"MCP fallback вернул ошибку: {fallback_data['error']}")
                        else:
                            logger.error(f"MCP сервер вернул ошибку: {error_info}")
                        return None
                else:
                    logger.error(f"MCP сервер вернул статус {response.status_code}: {response.text[:200]}")
                    return None
                    
        except Exception as e:
            logger.error(f"Ошибка получения данных через MCP сервер: {e}")
            return None
    
    def _extract_content_from_mcp_result(self, result: Any) -> str:
        """
        Извлекает текстовый контент из результата MCP.
        MCP Notion может возвращать данные в формате enhanced markdown с тегами <meeting-notes>.
        """
        if isinstance(result, dict):
            # MCP Notion может возвращать enhanced markdown в поле "text" (приоритет)
            if "text" in result:
                text_content = result["text"]
                if isinstance(text_content, str):
                    # Если это строка, возможно это уже enhanced markdown с тегами
                    return text_content
                # Если это не строка, рекурсивно обрабатываем
                return self._extract_content_from_mcp_result(text_content)
            
            # MCP Notion может возвращать enhanced markdown в поле "content"
            if "content" in result:
                content = result["content"]
                if isinstance(content, str):
                    # Если это строка, возможно это уже markdown с тегами
                    return content
                elif isinstance(content, list):
                    # Если это массив блоков, извлекаем текст
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            # Извлекаем текст из блока
                            block_type = block.get("type")
                            if block_type:
                                block_data = block.get(block_type, {})
                                # Пробуем разные форматы блоков
                                if "rich_text" in block_data:
                                    for text in block_data["rich_text"]:
                                        if isinstance(text, dict):
                                            plain_text = text.get("plain_text", "")
                                            if plain_text:
                                                text_parts.append(plain_text)
                                elif "text" in block_data:
                                    text_parts.append(str(block_data["text"]))
                    return "\n".join(text_parts)
            
            # Пробуем другие поля
            if "markdown" in result:
                return str(result["markdown"])
            
            # Если это объект страницы, пробуем получить блоки
            if "blocks" in result:
                return self._extract_content_from_mcp_result(result["blocks"])
            
            # Если есть children, рекурсивно обрабатываем
            if "children" in result:
                return self._extract_content_from_mcp_result(result["children"])
        
        elif isinstance(result, str):
            return result
        
        elif isinstance(result, list):
            # Если это список блоков
            text_parts = []
            for item in result:
                text_parts.append(self._extract_content_from_mcp_result(item))
            return "\n".join(filter(None, text_parts))
        
        # Fallback: преобразуем в строку
        return str(result) if result else ""
    
    def extract_last_meeting_from_mcp_content(self, mcp_content: str) -> Optional[Dict[str, Any]]:
        """
        Извлекает последнюю встречу из MCP Notion enhanced markdown.
        
        Согласно техническому отчету: MCP преобразует AI Meeting Notes в Markdown,
        который часто обрамляется тегами <summary> или заголовками # Summary.
        Использует регулярные выражения для парсинга этого текста.
        
        Ищет <meeting-notes> блоки, внутри них <transcript> и <summary>.
        Также ищет заголовки Markdown (# Summary, ## Summary и т.д.).
        Возвращает последний meeting-notes блок с приоритетом: transcript > summary > весь контент.
        
        Args:
            mcp_content: Enhanced markdown контент от MCP Notion
            
        Returns:
            Словарь с данными встречи:
            {
                "content": str,  # Текст встречи (transcript, summary или весь контент)
                "type": str,     # "transcript", "summary" или "full"
                "block_index": int  # Индекс найденного блока (для отладки)
            }
            или None, если встречи не найдены
        """
        import re
        
        if not mcp_content or not isinstance(mcp_content, str):
            logger.warning("MCP контент пустой или не является строкой")
            return None
        
        # Согласно техническому отчету: ищем секцию, начинающуюся с # Summary
        # или тега <summary> и захватываем текст до следующего заголовка
        
        # Метод 1: Ищем все блоки <meeting-notes>
        meeting_notes_pattern = r'<meeting-notes[^>]*>([\s\S]*?)</meeting-notes>'
        meeting_blocks = re.findall(meeting_notes_pattern, mcp_content, re.IGNORECASE)
        
        if not meeting_blocks:
            # Fallback: ищем transcript или summary напрямую в контенте
            logger.debug("Блоки <meeting-notes> не найдены, ищем transcript/summary напрямую")
            
            # Ищем теги <transcript> и <summary>
            transcript_pattern = r'<transcript[^>]*>([\s\S]*?)</transcript>'
            summary_pattern = r'<summary[^>]*>([\s\S]*?)</summary>'
            
            transcript_match = re.search(transcript_pattern, mcp_content, re.IGNORECASE)
            summary_match = re.search(summary_pattern, mcp_content, re.IGNORECASE)
            
            if transcript_match:
                content = transcript_match.group(1).strip()
                logger.info("Найден transcript напрямую в контенте")
                return {
                    "content": content,
                    "type": "transcript",
                    "block_index": -1
                }
            elif summary_match:
                content = summary_match.group(1).strip()
                logger.info("Найден summary напрямую в контенте")
                return {
                    "content": content,
                    "type": "summary",
                    "block_index": -1
                }
            
            # Согласно отчету: ищем заголовки Markdown (# Summary, ## Summary)
            # Захватываем текст до следующего заголовка
            summary_header_pattern = r'^#+\s*(?:Summary|Саммари|Резюме)\s*\n([\s\S]*?)(?=^#+\s|\Z)'
            summary_header_match = re.search(summary_header_pattern, mcp_content, re.MULTILINE | re.IGNORECASE)
            
            if summary_header_match:
                content = summary_header_match.group(1).strip()
                logger.info("Найден summary через заголовок Markdown (# Summary)")
                return {
                    "content": content,
                    "type": "summary",
                    "block_index": -1
                }
            
            logger.warning("Не найдено ни meeting-notes блоков, ни transcript/summary")
            return None
        
        # Берем последний блок (самая свежая встреча)
        last_block = meeting_blocks[-1]
        logger.info(f"Найдено {len(meeting_blocks)} блоков meeting-notes, используем последний")
        
        # Внутри блока ищем transcript и summary
        transcript_pattern = r'<transcript[^>]*>([\s\S]*?)</transcript>'
        summary_pattern = r'<summary[^>]*>([\s\S]*?)</summary>'
        
        transcript_match = re.search(transcript_pattern, last_block, re.IGNORECASE)
        summary_match = re.search(summary_pattern, last_block, re.IGNORECASE)
        
        # Приоритет: transcript > summary > весь контент блока
        if transcript_match:
            content = transcript_match.group(1).strip()
            logger.info("Найден transcript в последнем meeting-notes блоке")
            return {
                "content": content,
                "type": "transcript",
                "block_index": len(meeting_blocks) - 1
            }
        elif summary_match:
            content = summary_match.group(1).strip()
            logger.info("Найден summary в последнем meeting-notes блоке")
            return {
                "content": content,
                "type": "summary",
                "block_index": len(meeting_blocks) - 1
            }
        else:
            # Также проверяем заголовки Markdown внутри блока
            summary_header_pattern = r'^#+\s*(?:Summary|Саммари|Резюме)\s*\n([\s\S]*?)(?=^#+\s|\Z)'
            summary_header_match = re.search(summary_header_pattern, last_block, re.MULTILINE | re.IGNORECASE)
            
            if summary_header_match:
                content = summary_header_match.group(1).strip()
                logger.info("Найден summary через заголовок Markdown внутри meeting-notes блока")
                return {
                    "content": content,
                    "type": "summary",
                    "block_index": len(meeting_blocks) - 1
                }
            
            # Используем весь контент блока
            content = last_block.strip()
            logger.info("Используем весь контент последнего meeting-notes блока (transcript/summary не найдены)")
            return {
                "content": content,
                "type": "full",
                "block_index": len(meeting_blocks) - 1
            }