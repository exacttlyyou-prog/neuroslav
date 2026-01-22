"""
Асинхронный сервис для работы с Notion API с ретраями.
По умолчанию использует MCP Notion для получения контента.
"""
from notion_client import AsyncClient
from loguru import logger
from typing import Dict, Any
import asyncio
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from core.config import get_settings
from core.schemas import ActionItem


class NotionService:
    """Сервис для работы с Notion API."""
    
    def __init__(self):
        settings = get_settings()
        if not settings.notion_token:
            raise ValueError("NOTION_TOKEN не установлен в переменных окружения")
        # Используем актуальную версию API 2025-09-03
        self.client = AsyncClient(auth=settings.notion_token, notion_version="2025-09-03")
        self.people_db_id = settings.notion_people_db_id
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def get_page_content(self, page_id: str) -> str:
        """
        Получает контент страницы Notion с ретраями.
        
        Args:
            page_id: ID страницы Notion
            
        Returns:
            Текст контента страницы
        """
        try:
            page = await self.client.pages.retrieve(page_id)
            blocks = await self.client.blocks.children.list(page_id)
            
            # Извлекаем текст из блоков
            content_parts = []
            for block in blocks.get("results", []):
                block_type = block.get("type")
                if block_type == "paragraph":
                    rich_text = block.get("paragraph", {}).get("rich_text", [])
                    text = "".join([rt.get("plain_text", "") for rt in rich_text])
                    if text:
                        content_parts.append(text)
                elif block_type == "heading_1":
                    rich_text = block.get("heading_1", {}).get("rich_text", [])
                    text = "".join([rt.get("plain_text", "") for rt in rich_text])
                    if text:
                        content_parts.append(f"# {text}")
                elif block_type == "heading_2":
                    rich_text = block.get("heading_2", {}).get("rich_text", [])
                    text = "".join([rt.get("plain_text", "") for rt in rich_text])
                    if text:
                        content_parts.append(f"## {text}")
            
            content = "\n\n".join(content_parts)
            logger.info(f"Получен контент страницы {page_id}, длина: {len(content)} символов")
            return content
            
        except Exception as e:
            logger.error(f"Ошибка при получении контента страницы {page_id}: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def get_last_meeting_content(self, page_id: str) -> str:
        """
        Читает последнюю встречу из страницы Notion (снизу вверх до заголовка).
        
        Args:
            page_id: ID страницы Notion
            
        Returns:
            Текст последней встречи
        """
        try:
            # Получаем все блоки страницы
            blocks_response = await self.client.blocks.children.list(page_id)
            all_blocks = blocks_response.get("results", [])
            
            if not all_blocks:
                logger.warning(f"Страница {page_id} не содержит блоков")
                return ""
            
            # Идем снизу вверх, собираем блоки до первого заголовка
            content_parts = []
            found_heading = False
            
            for block in reversed(all_blocks):
                block_type = block.get("type")
                
                # Если нашли заголовок (h1 или h2), останавливаемся
                if block_type in ["heading_1", "heading_2"]:
                    if found_heading:
                        # Это начало предыдущей встречи, останавливаемся
                        break
                    found_heading = True
                    rich_text = block.get(block_type, {}).get("rich_text", [])
                    text = "".join([rt.get("plain_text", "") for rt in rich_text])
                    if text:
                        prefix = "#" if block_type == "heading_1" else "##"
                        content_parts.insert(0, f"{prefix} {text}")
                elif block_type == "paragraph":
                    rich_text = block.get("paragraph", {}).get("rich_text", [])
                    text = "".join([rt.get("plain_text", "") for rt in rich_text])
                    if text:
                        content_parts.insert(0, text)
            
            content = "\n\n".join(content_parts)
            logger.info(f"Извлечена последняя встреча из страницы {page_id}, длина: {len(content)} символов")
            return content
            
        except Exception as e:
            logger.error(f"Ошибка при получении последней встречи из страницы {page_id}: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def create_tasks(
        self,
        page_id: str,
        action_items: list[ActionItem],
        database_id: str | None = None
    ) -> list[str]:
        """
        Создает задачи (To-Do блоки) в Notion с ретраями.
        
        Args:
            page_id: ID страницы, куда добавлять задачи
            action_items: Список задач для создания
            database_id: Опционально, ID базы данных для создания записей
            
        Returns:
            Список ID созданных задач
        """
        created_task_ids = []
        
        try:
            for item in action_items:
                # Создаем To-Do блок
                block_data: Dict[str, Any] = {
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": item.text}
                            }
                        ],
                        "checked": False
                    }
                }
                
                # Добавляем приоритет в свойства, если есть database_id
                if database_id:
                    # Создаем страницу в базе данных
                    page_properties: Dict[str, Any] = {
                        "Name": {
                            "title": [{"text": {"content": item.text}}]
                        }
                    }
                    
                    if item.priority:
                        page_properties["Priority"] = {  # type: ignore
                            "select": {"name": str(item.priority)}
                        }
                    
                    if item.assignee:
                        page_properties["Assignee"] = {
                            "rich_text": [{"text": {"content": item.assignee}}]
                        }
                    
                    new_page = await self.client.pages.create(
                        parent={"database_id": database_id},
                        properties=page_properties
                    )
                    created_task_ids.append(new_page["id"])
                else:
                    # Просто добавляем блок на страницу
                    new_block = await self.client.blocks.children.append(
                        block_id=page_id,
                        children=[block_data]
                    )
                    created_task_ids.append(new_block["results"][0]["id"])
            
            logger.info(f"Создано {len(created_task_ids)} задач в Notion")
            return created_task_ids
            
        except Exception as e:
            logger.error(f"Ошибка при создании задач в Notion: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def _check_object_type(self, object_id: str) -> str:
        """
        Проверяет, является ли объект базой данных или страницей.
        
        Args:
            object_id: ID объекта Notion
            
        Returns:
            'database' или 'page'
        """
        try:
            # Пробуем получить как страницу
            page = await self.client.pages.retrieve(object_id)
            if page.get("object") == "database":
                logger.debug(f"Объект {object_id} является базой данных")
                return "database"
            logger.debug(f"Объект {object_id} является страницей")
            return "page"
        except Exception as e:
            # Если не страница, пробуем как базу данных
            try:
                db = await self.client.databases.retrieve(object_id)
                if db.get("object") == "database":
                    logger.debug(f"Объект {object_id} является базой данных")
                    return "database"
            except Exception as db_error:
                logger.debug(f"Ошибка при проверке типа объекта {object_id}: {e}, {db_error}")
        
        # По умолчанию считаем страницей
        logger.debug(f"Объект {object_id} считается страницей по умолчанию")
        return "page"
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def get_latest_from_database(
        self, database_id: str
    ) -> tuple[str, str, str]:
        """
        Получает последнюю запись из базы данных с сортировкой O(1).
        
        Args:
            database_id: ID базы данных
            
        Returns:
            Кортеж (page_id, title, content)
        """
        try:
            # Используем прямой HTTP запрос, так как notion-client не имеет метода query
            import httpx
            settings = get_settings()
            headers = {
                "Authorization": f"Bearer {settings.notion_token}",
                "Notion-Version": "2025-09-03",
                "Content-Type": "application/json"
            }
            
            # Запрос с серверной сортировкой по времени создания
            async with httpx.AsyncClient() as client:
                http_response = await client.post(
                    f"https://api.notion.com/v1/databases/{database_id}/query",
                    headers=headers,
                    json={
                        "page_size": 1,  # Только последняя запись
                        "sorts": [
                            {
                                "timestamp": "created_time",
                                "direction": "descending"
                            }
                        ]
                    }
                )
                http_response.raise_for_status()
                data = http_response.json()
            
            results = data.get("results", [])
            if not results:
                logger.warning(f"База данных {database_id} пуста")
                return ("", "", "")
            
            latest_page = results[0]
            page_id = latest_page["id"]
            
            # Извлекаем заголовок из свойств
            title = "Встреча"
            for prop_name, prop_val in latest_page.get("properties", {}).items():
                if prop_val.get("type") == "title":
                    title_parts = prop_val.get("title", [])
                    if title_parts:
                        title = title_parts[0].get("plain_text", "Встреча")
                    break
            
            logger.info(f"Найдена последняя запись в БД: '{title}' (ID: {page_id})")
            
            # Получаем контент страницы
            # Для meeting-notes нужен MCP
            block_id, _, content = await self._get_content_via_mcp(page_id)
            if not content or len(content.strip()) < 50:
                # Fallback: получаем блоки через обычный API
                logger.debug("MCP не вернул контент, используем обычный API для блоков")
                blocks_response = await self.client.blocks.children.list(page_id)
                blocks = blocks_response.get("results", [])
                content_parts = []
                for block in blocks:
                    block_type = block.get("type")
                    if block_type in ["paragraph", "heading_1", "heading_2", "heading_3"]:
                        rich_text = block.get(block_type, {}).get("rich_text", [])
                        text = "".join([rt.get("plain_text", "") for rt in rich_text])
                        if text:
                            if block_type.startswith("heading"):
                                level = block_type.split("_")[1]
                                text = f"{'#' * int(level)} {text}"
                            content_parts.append(text)
                content = "\n\n".join(content_parts)
            
            if content and len(content.strip()) >= 50:
                logger.info(f"✅ Контент получен из БД: '{title}' ({len(content)} символов)")
                return (page_id, title, content)
            else:
                logger.warning(f"Контент страницы {page_id} слишком короткий или пустой")
                return (page_id, title, "")
            
        except Exception as e:
            logger.error(f"Ошибка при запросе базы данных {database_id}: {e}")
            return ("", "", "")
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def _get_content_via_mcp(self, page_id: str) -> tuple[str, str, str]:
        """
        Получает контент страницы через разные методы.
        Приоритет: Playwright (браузер) -> Remote MCP -> Экспорт -> Прямой API.
        
        Returns:
            Кортеж (block_id, title, content): данные встречи или ("", "", "") для fallback
        """
        # Метод 1: Playwright (браузер) - получает полный контент, включая transcription
        try:
            logger.info("🔍 Метод 1: Playwright (браузер)...")
            from integrations.notion_playwright import NotionPlaywright
            playwright = NotionPlaywright()
            
            content = await playwright.get_page_by_id(page_id)
            
            if content and len(content.strip()) >= 100:
                logger.info(f"✅ Playwright вернул контент: {len(content)} символов")
                
                # Парсим meeting-notes из контента
                block_id, title, parsed_content = self._extract_last_meeting_from_mcp_content(content, page_id)
                if parsed_content and len(parsed_content.strip()) >= 100:
                    logger.info(f"✅ Извлечен контент meeting-notes через Playwright: '{title}' ({len(parsed_content)} символов)")
                    return (block_id, title, parsed_content)
                # Если парсинг не нашел meeting-notes, но есть контент, используем его
                elif content and len(content.strip()) >= 200:
                    # Ищем заголовок в контенте
                    title = "Встреча"
                    lines = content.split('\n')
                    for line in lines[:5]:
                        if line.strip() and len(line.strip()) > 10:
                            title = line.strip()[:100]
                            break
                    return (page_id, title, content)
        except Exception as playwright_error:
            logger.debug(f"Playwright: {playwright_error}")
        
        # Метод 2: Remote MCP с notion-fetch (единственный способ получить transcription блоки)
        try:
            logger.info("🔍 Метод 2: Remote MCP с notion-fetch...")
            from integrations.mcp_client import MCPNotionClient
            mcp_client = MCPNotionClient()
            
            # Пробуем получить через remote MCP (SSE/HTTP)
            mcp_data = await mcp_client.fetch_page_via_remote_mcp(page_id, timeout=60)
            
            if mcp_data and mcp_data.get('text'):
                text_content = mcp_data['text']
                logger.info(f"✅ Remote MCP вернул контент: {len(text_content)} символов")
                
                # Парсим meeting-notes из контента
                block_id, title, content = self._extract_last_meeting_from_mcp_content(text_content, page_id)
                if content and len(content.strip()) >= 100:
                    logger.info(f"✅ Извлечен контент meeting-notes: '{title}' ({len(content)} символов)")
                    return (block_id, title, content)
        except Exception as mcp_error:
            logger.debug(f"Remote MCP: {mcp_error}")
        
        # Метод 2: Экспорт страницы (может содержать transcription данные)
        try:
            logger.info("🔍 Метод 2: Экспорт страницы Notion...")
            from integrations.notion_export import NotionExporter
            exporter = NotionExporter()
            content = await exporter.export_page(page_id)
            
            if content and len(content.strip()) >= 100:
                logger.info(f"✅ Получен контент через экспорт: {len(content)} символов")
                # Парсим meeting-notes из экспортированного контента
                block_id, title, parsed_content = self._extract_last_meeting_from_mcp_content(content, page_id)
                if parsed_content and len(parsed_content.strip()) >= 100:
                    return (block_id, title, parsed_content)
        except Exception as export_error:
            logger.debug(f"Экспорт: {export_error}")
        
        # Метод 3: Прямой API запрос (получаем все доступные данные)
        try:
            logger.info("🔍 Метод 3: Прямой API запрос к Notion...")
            from integrations.notion_direct_api import NotionDirectAPI
            direct_api = NotionDirectAPI()
            content = await direct_api.get_page_all_data(page_id)
            
            if content and len(content.strip()) >= 50:
                logger.info(f"✅ Получен контент через прямой API: {len(content)} символов")
                try:
                    page = await self.client.pages.retrieve(page_id)
                    title = "Встреча"
                    if "properties" in page:
                        for prop_name, prop_val in page["properties"].items():
                            if prop_val.get("type") == "title":
                                title_parts = prop_val.get("title", [])
                                if title_parts:
                                    title = title_parts[0].get("plain_text", "Встреча")
                                    break
                    return (page_id, title, content)
                except Exception:
                    return (page_id, "Встреча", content)
        except Exception as e:
            logger.debug(f"Прямой API: {e}")
        
        # Если ничего не сработало, возвращаем пустой результат
        return ("", "", "")
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def get_or_create_user(self, tg_user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Получает или создает пользователя в базе People.
        
        Args:
            tg_user_data: Словарь с данными пользователя Telegram:
                - id: Chat ID пользователя
                - first_name: Имя
                - last_name: Фамилия (опционально)
                - username: @username (опционально)
        
        Returns:
            Словарь с данными пользователя из Notion:
                - page_id: ID страницы в Notion
                - status: Статус пользователя (Active, Pending, Blocked)
                - name: Имя пользователя
                - telegram: @username
                - chat_id: Chat ID
                - is_new: True, если пользователь был только что создан
        """
        if not self.people_db_id:
            raise ValueError("NOTION_PEOPLE_DB_ID не установлен в переменных окружения")
        
        try:
            chat_id = str(tg_user_data.get('id'))
            username = tg_user_data.get('username', '')
            first_name = tg_user_data.get('first_name', '')
            last_name = tg_user_data.get('last_name', '')
            full_name = f"{first_name} {last_name}".strip() if last_name else first_name
            
            # 1. Поиск пользователя по ChatID (предпочтительно)
            logger.info(f"Поиск пользователя по ChatID: {chat_id}")
            # Используем прямой HTTP запрос, так как notion-client не имеет метода query
            import httpx
            settings = get_settings()
            headers = {
                "Authorization": f"Bearer {settings.notion_token}",
                "Notion-Version": "2025-09-03",
                "Content-Type": "application/json"
            }
            async with httpx.AsyncClient() as client:
                http_response = await client.post(
                    f"https://api.notion.com/v1/databases/{self.people_db_id}/query",
                    headers=headers,
                    json={
                        "filter": {
                            "property": "ChatID",
                            "rich_text": {
                                "equals": chat_id
                            }
                        }
                    }
                )
                http_response.raise_for_status()
                response_data = http_response.json()
            response = response_data
            
            if response.get('results') and len(response['results']) > 0:
                # Пользователь найден по ChatID
                page = response['results'][0]
                properties = page.get('properties', {})
                
                # Извлекаем данные
                status_prop = properties.get('Status') or properties.get('status')
                status = 'Unknown'
                if status_prop:
                    if status_prop.get('type') == 'select' and status_prop.get('select'):
                        status = status_prop['select'].get('name', 'Unknown')
                
                name_prop = properties.get('Name') or properties.get('name')
                name = full_name
                if name_prop and name_prop.get('type') == 'title':
                    title_list = name_prop.get('title', [])
                    if title_list:
                        name = title_list[0].get('plain_text', full_name)
                
                telegram_prop = properties.get('Telegram') or properties.get('telegram')
                telegram_username = username
                if telegram_prop:
                    if telegram_prop.get('type') == 'rich_text':
                        rich_text = telegram_prop.get('rich_text', [])
                        if rich_text:
                            telegram_username = rich_text[0].get('plain_text', username)
                
                logger.info(f"Пользователь найден: {name} (Status: {status})")
                return {
                    'page_id': page['id'],
                    'status': status,
                    'name': name,
                    'telegram': telegram_username,
                    'chat_id': chat_id,
                    'is_new': False
                }
            
            # 2. Поиск по Telegram username (если есть)
            if username:
                logger.info(f"Поиск пользователя по Telegram username: @{username}")
                # Используем прямой HTTP запрос, так как notion-client не имеет метода query
                import httpx
                settings = get_settings()
                headers = {
                    "Authorization": f"Bearer {settings.notion_token}",
                    "Notion-Version": "2025-09-03",
                    "Content-Type": "application/json"
                }
                async with httpx.AsyncClient() as client:
                    http_response = await client.post(
                        f"https://api.notion.com/v1/databases/{self.people_db_id}/query",
                        headers=headers,
                        json={
                            "filter": {
                                "property": "Telegram",
                                "rich_text": {
                                    "contains": username
                                }
                            }
                        }
                    )
                    http_response.raise_for_status()
                    response_data = http_response.json()
                response = response_data
                
                if response.get('results') and len(response['results']) > 0:
                    # Пользователь найден по username
                    page = response['results'][0]
                    properties = page.get('properties', {})
                    
                    status_prop = properties.get('Status') or properties.get('status')
                    status = 'Unknown'
                    if status_prop:
                        if status_prop.get('type') == 'select' and status_prop.get('select'):
                            status = status_prop['select'].get('name', 'Unknown')
                    
                    name_prop = properties.get('Name') or properties.get('name')
                    name = full_name
                    if name_prop and name_prop.get('type') == 'title':
                        title_list = name_prop.get('title', [])
                        if title_list:
                            name = title_list[0].get('plain_text', full_name)
                    
                    # Обновляем ChatID, если его нет
                    chat_id_prop = properties.get('ChatID') or properties.get('chat_id')
                    if not chat_id_prop or not chat_id_prop.get('rich_text'):
                        # Обновляем ChatID
                        await self.client.pages.update(
                            page_id=page['id'],
                            properties={
                                "ChatID": {
                                    "rich_text": [
                                        {
                                            "text": {
                                                "content": chat_id
                                            }
                                        }
                                    ]
                                }
                            }
                        )
                    
                    logger.info(f"Пользователь найден по username: {name} (Status: {status})")
                    return {
                        'page_id': page['id'],
                        'status': status,
                        'name': name,
                        'telegram': username,
                        'chat_id': chat_id,
                        'is_new': False
                    }
            
            # 3. Пользователь не найден - создаем новую запись
            logger.info(f"Создание нового пользователя: {full_name} (@{username})")
            
            # Формируем свойства для новой страницы
            properties = {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": full_name
                            }
                        }
                    ]
                },
                "ChatID": {
                    "rich_text": [
                        {
                            "text": {
                                "content": chat_id
                            }
                        }
                    ]
                },
                "Status": {
                    "select": {
                        "name": "Pending"
                    }
                },
                "Role": {
                    "rich_text": [
                        {
                            "text": {
                                "content": "New User"
                            }
                        }
                    ]
                }
            }
            
            # Добавляем Telegram username, если есть
            if username:
                properties["Telegram"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": username
                            }
                        }
                    ]
                }
            
            # Создаем страницу в базе данных
            new_page = await self.client.pages.create(
                parent={
                    "database_id": self.people_db_id
                },
                properties=properties
            )
            
            logger.info(f"Создан новый пользователь: {full_name} (Status: Pending)")
            return {
                'page_id': new_page['id'],
                'status': 'Pending',
                'name': full_name,
                'telegram': username,
                'chat_id': chat_id,
                'is_new': True
            }
            
        except Exception as e:
            logger.error(f"Ошибка при получении/создании пользователя: {e}")
            raise
    
    def _extract_last_meeting_from_mcp_content(self, text_content: str, page_id: str) -> tuple[str, str, str]:
        """
        Извлекает последнюю встречу из контента, полученного через MCP Notion или экспорт.
        Поддерживает разные форматы: <meeting-notes> блоки, HTML, markdown.
        
        Args:
            text_content: Полный текст контента страницы
            page_id: ID страницы
            
        Returns:
            Кортеж (block_id, title, content)
        """
        import re
        
        # Если это HTML, сначала очищаем от JavaScript и извлекаем текстовый контент
        if "<html" in text_content.lower() or "<script" in text_content.lower():
            # Пробуем использовать BeautifulSoup для парсинга HTML
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(text_content, 'html.parser')
                
                # Убираем script и style теги
                for script in soup(["script", "style", "noscript"]):
                    script.decompose()
                
                # Извлекаем текст из body
                body = soup.find('body')
                if body:
                    body_text = body.get_text(separator=' ', strip=True)
                    # Ищем summary/transcript в тексте body
                    if body_text and len(body_text) > 200:
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
                            title = "Встреча"
                            title_match = re.search(r'(?:meeting|встреча|Meeting)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-()]{10,200})', body_text, re.IGNORECASE)
                            if title_match:
                                title = title_match.group(1).strip()[:100]
                            
                            content = "\n\n".join(content_parts)
                            logger.info(f"✅ Извлечен контент из HTML через BeautifulSoup: '{title}' ({len(content)} символов)")
                            return (page_id, title, content)
            except ImportError:
                logger.debug("BeautifulSoup не установлен, используем regex парсинг")
            except Exception as bs_error:
                logger.debug(f"Ошибка BeautifulSoup: {bs_error}")
            
            # Fallback: убираем все script и style теги через regex
            clean_content = re.sub(r'<script[^>]*>.*?</script>', '', text_content, flags=re.DOTALL | re.IGNORECASE)
            clean_content = re.sub(r'<style[^>]*>.*?</style>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
            clean_content = re.sub(r'<noscript[^>]*>.*?</noscript>', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
            
            # Ищем JSON данные в HTML (Notion может встраивать данные)
            json_patterns = [
                r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
                r'window\.__notion_html_async\.push\([^,]+,\s*({.*?})\)',
                r'data-notion-page-id[^>]*data-content[^>]*="([^"]+)"',
            ]
            
            for pattern in json_patterns:
                matches = re.finditer(pattern, clean_content, re.DOTALL)
                for match in matches:
                    try:
                        json_str = match.group(1).strip()
                        if json_str.startswith('{'):
                            import json
                            data = json.loads(json_str)
                            # Ищем meeting-notes данные в JSON
                            if isinstance(data, dict):
                                # Рекурсивно ищем summary/transcript
                                def find_text(obj, depth=0):
                                    if depth > 10:
                                        return None
                                    if isinstance(obj, dict):
                                        for k, v in obj.items():
                                            if any(kw in str(k).lower() for kw in ['summary', 'transcript', 'notes']):
                                                if isinstance(v, str) and len(v) > 100:
                                                    return v
                                            result = find_text(v, depth + 1)
                                            if result:
                                                return result
                                    elif isinstance(obj, list):
                                        for item in obj:
                                            result = find_text(item, depth + 1)
                                            if result:
                                                return result
                                    return None
                                
                                found_text = find_text(data)
                                if found_text:
                                    logger.info(f"✅ Найден контент в JSON: {len(found_text)} символов")
                                    return (page_id, "Встреча", found_text)
                    except Exception:
                        continue
            
            # Если JSON не найден, извлекаем текст из HTML тегов
            # Сначала пробуем извлечь текст из видимых элементов (не из скриптов)
            # Ищем текст в body, но не в script/style
            body_match = re.search(r'<body[^>]*>(.*?)</body>', text_content, re.DOTALL | re.IGNORECASE)
            if body_match:
                body_content = body_match.group(1)
                # Убираем script и style из body
                body_content = re.sub(r'<script[^>]*>.*?</script>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
                body_content = re.sub(r'<style[^>]*>.*?</style>', '', body_content, flags=re.DOTALL | re.IGNORECASE)
                
                # Извлекаем текст из HTML элементов
                # Ищем текст в div, span, p и других элементах
                text_elements = re.findall(r'<[^>]+>([^<]+)</[^>]+>', body_content)
                visible_text = ' '.join([elem.strip() for elem in text_elements if elem.strip() and len(elem.strip()) > 10])
                
                if visible_text and len(visible_text) > 200:
                    # Ищем summary/transcript в видимом тексте
                    summary_match = re.search(r'(?:summary|Summary|резюме|Резюме)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-()]{300,5000})', visible_text, re.IGNORECASE)
                    transcript_match = re.search(r'(?:transcript|Transcript|транскрипт|Транскрипт)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-()]{500,10000})', visible_text, re.IGNORECASE)
                    
                    content_parts = []
                    if summary_match:
                        summary_text = summary_match.group(1).strip()
                        summary_text = re.sub(r'\s+', ' ', summary_text)
                        if len(summary_text) > 200 and not any(kw in summary_text.lower() for kw in ['function', 'var ', 'const ', 'window.']):
                            content_parts.append(f"## Summary\n{summary_text}")
                    
                    if transcript_match:
                        transcript_text = transcript_match.group(1).strip()
                        transcript_text = re.sub(r'\s+', ' ', transcript_text)
                        if len(transcript_text) > 500 and not any(kw in transcript_text.lower() for kw in ['function', 'var ', 'const ', 'window.']):
                            content_parts.append(f"## Transcript\n{transcript_text}")
                    
                    if content_parts:
                        title = "Встреча"
                        title_match = re.search(r'(?:meeting|встреча|Meeting)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-()]{10,200})', visible_text, re.IGNORECASE)
                        if title_match:
                            title = title_match.group(1).strip()[:100]
                        
                        content = "\n\n".join(content_parts)
                        logger.info(f"✅ Извлечен контент из HTML body: '{title}' ({len(content)} символов)")
                        return (page_id, title, content)
            
            # Если body не помог, убираем все HTML теги, оставляя только текст
            clean_content = re.sub(r'<[^>]+>', ' ', clean_content)
            clean_content = re.sub(r'&[a-z]+;', ' ', clean_content)  # HTML entities
            clean_content = re.sub(r'\s+', ' ', clean_content).strip()
            
            # Если после очистки остался осмысленный текст, используем его
            if len(clean_content) > 200 and not any(kw in clean_content for kw in ['function', 'var ', 'const ', 'window.', 'document.', 'JSON.stringify']):
                # Ищем summary/transcript в очищенном тексте
                summary_match = re.search(r'(?:summary|Summary|резюме|Резюме)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-()]{300,5000})', clean_content, re.IGNORECASE)
                transcript_match = re.search(r'(?:transcript|Transcript|транскрипт|Транскрипт)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-()]{500,10000})', clean_content, re.IGNORECASE)
                
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
                    title = "Встреча"
                    title_match = re.search(r'(?:meeting|встреча|Meeting)[\s:"]*([А-Яа-яA-Za-z0-9\s.,!?;:—–\-()]{10,200})', clean_content, re.IGNORECASE)
                    if title_match:
                        title = title_match.group(1).strip()[:100]
                    
                    content = "\n\n".join(content_parts)
                    logger.info(f"✅ Извлечен контент из HTML: '{title}' ({len(content)} символов)")
                    return (page_id, title, content)
            
            # Если очистка не помогла, используем оригинальный контент для поиска meeting-notes
            text_content = clean_content
        
        # Ищем все meeting-notes блоки в тексте
        # Паттерн 1: Стандартный формат с <meeting-notes> тегами
        meeting_pattern1 = r'<meeting-notes>(.*?)</meeting-notes>'
        meetings1 = list(re.finditer(meeting_pattern1, text_content, re.DOTALL))
        
        # Паттерн 2: Альтернативный формат с заголовком
        meeting_pattern2 = r'<meeting-notes>\s*\n\s*\*\*([^*]+)\*\*'
        meetings2 = list(re.finditer(meeting_pattern2, text_content, re.MULTILINE | re.DOTALL))
        
        # Используем первый паттерн (более надежный)
        meetings = meetings1 if meetings1 else meetings2
        
        if meetings:
            # Берем последний meeting-notes блок (самая свежая встреча)
            last_meeting = meetings[-1]
            
            # Извлекаем контент блока
            if meetings1:
                # Паттерн 1: уже извлекли контент между тегами
                meeting_content = last_meeting.group(1).strip()
                # Извлекаем заголовок (первая строка или текст до первого тега)
                title = "Встреча"
                first_line = meeting_content.split('\n')[0].strip()
                if first_line:
                    # Убираем markdown форматирование (**bold**, # heading, mention теги)
                    title = re.sub(r'\*\*|\*|#|<[^>]+>', '', first_line).strip()
                    if not title or len(title) < 3:
                        title = "Встреча"
            else:
                # Паттерн 2: заголовок в группе
                title = last_meeting.group(1).strip() if last_meeting.lastindex else "Встреча"
                start_pos = last_meeting.start()
                closing_tag_pos = text_content.find("</meeting-notes>", start_pos)
                if closing_tag_pos > start_pos:
                    meeting_content = text_content[last_meeting.end():closing_tag_pos].strip()
                else:
                    meeting_content = text_content[last_meeting.end():].strip()
            
            # Извлекаем содержимое из тегов согласно документации
            summary_match = re.search(r'<summary>(.*?)</summary>', meeting_content, re.DOTALL)
            notes_match = re.search(r'<notes>(.*?)</notes>', meeting_content, re.DOTALL)
            transcript_match = re.search(r'<transcript>(.*?)</transcript>', meeting_content, re.DOTALL)
            
            # Формируем читаемый контент: заголовок + summary + notes + transcript
            readable_content_parts = [f"# {title}"]
            
            if summary_match:
                summary_text = summary_match.group(1).strip()
                # Убираем лишние отступы (контент внутри тегов должен быть с отступом)
                summary_text = re.sub(r'^\t+', '', summary_text, flags=re.MULTILINE)
                if summary_text and summary_text != "<empty-block/>":
                    readable_content_parts.append(f"\n## Summary\n{summary_text}")
            
            if notes_match:
                notes_text = notes_match.group(1).strip()
                notes_text = re.sub(r'^\t+', '', notes_text, flags=re.MULTILINE)
                if notes_text and notes_text != "<empty-block/>":
                    readable_content_parts.append(f"\n## Notes\n{notes_text}")
            
            if transcript_match:
                transcript_text = transcript_match.group(1).strip()
                # Убираем лишние отступы
                transcript_text = re.sub(r'^\t+', '', transcript_text, flags=re.MULTILINE)
                if transcript_text and transcript_text != "<empty-block/>":
                    readable_content_parts.append(f"\n## Transcript\n{transcript_text}")
            
            # Если есть хотя бы один из тегов, используем их
            if summary_match or notes_match or transcript_match:
                readable_content = "\n".join(readable_content_parts)
            else:
                # Если нет тегов, используем весь контент, очищая от XML-тегов
                readable_content = re.sub(r'<[^>]+>', '', meeting_content)
                readable_content = readable_content.strip()
                if not readable_content:
                    readable_content = title  # Fallback на заголовок
            
            # Убираем пустые блоки
            readable_content = re.sub(r'<empty-block/>\s*', '', readable_content)
            readable_content = readable_content.strip()
            
            if len(readable_content) >= 50:
                logger.info(f"✅ MCP: Найдена встреча '{title}' ({len(readable_content)} символов)")
                return (page_id, title, readable_content)
        
        # Fallback: ищем последний заголовок в формате **Заголовок** или # Заголовок
        lines = text_content.split("\n")
        last_meeting_start = -1
        title = "Последняя встреча"
        
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            
            # Ищем заголовок встречи в формате **Заголовок**
            if line.startswith("**") and "**" in line[2:]:
                title = line.strip("**").strip()
                last_meeting_start = i
                break
            elif line.startswith("#") and len(line) > 10:
                title = line.lstrip("#").strip()
                last_meeting_start = i
                break
        
        if last_meeting_start >= 0:
            content = "\n".join(lines[last_meeting_start:])
            # Очищаем от XML-тегов для читаемости
            content = re.sub(r'<[^>]+>', '', content)
            content = content.strip()
        else:
            # Берем последние 5000 символов и очищаем от XML-тегов
            content = text_content[-5000:] if len(text_content) > 5000 else text_content
            content = re.sub(r'<[^>]+>', '', content)
            content = content.strip()
        
        logger.info(f"MCP: Найдена встреча '{title}' ({len(content)} символов)")
        return (page_id, title, content)
    
    async def _get_last_blocks_optimized(
        self, page_id: str, last_n: int = 10
    ) -> list:
        """
        Оптимизированная пагинация: пропускаем промежуточные блоки,
        загружаем только последний сегмент для экономии памяти и времени.
        
        Args:
            page_id: ID страницы Notion
            last_n: Количество последних блоков для возврата
            
        Returns:
            Список последних N блоков
        """
        cursor = None
        last_chunk = []
        
        try:
            while True:
                response = await self.client.blocks.children.list(
                    block_id=page_id,
                    start_cursor=cursor,
                    page_size=100  # Максимальный размер страницы
                )
                
                results = response.get("results", [])
                if results:
                    last_chunk = results  # Сохраняем только последний кусок
                
                if not response.get("has_more"):
                    break
                
                cursor = response.get("next_cursor")
                # Не сохраняем промежуточные блоки - экономия памяти
                logger.debug(f"Пропущена страница пагинации, курсор: {cursor}")
            
            # Возвращаем последние N блоков
            return last_chunk[-last_n:] if last_chunk else []
            
        except Exception as e:
            logger.error(f"Ошибка при оптимизированной пагинации: {e}")
            return []
    
    async def _get_block_text_recursive(self, block_id: str, depth: int = 0) -> str:
        """
        Рекурсивно извлекает весь текст из блока и его детей.
        Пропускает transcription блоки (они не поддерживаются через API).
        """
        if depth > 5:  # Защита от слишком глубокой вложенности
            return ""
        
        try:
            content_parts = []
            next_cursor = None
            
            while True:
                try:
                    response = await self.client.blocks.children.list(
                        block_id=block_id,
                        start_cursor=next_cursor
                    )
                except Exception as e:
                    # Если это ошибка для transcription блока, пропускаем его
                    error_str = str(e).lower()
                    if "transcription" in error_str or "not supported" in error_str:
                        logger.debug(f"Пропускаем transcription блок {block_id}: {e}")
                        return "[Transcription блок - не поддерживается через API]"
                    raise
                
                blocks = response.get("results", [])
                
                for block in blocks:
                    b_type = block.get("type")
                    has_children = block.get("has_children", False)
                    block_id_inner = block.get("id")
                    
                    # Пропускаем unsupported блоки (transcription и т.д.)
                    if b_type == "unsupported":
                        unsupported_type = block.get("unsupported", {}).get("type", "unknown")
                        logger.debug(f"Пропускаем unsupported блок типа: {unsupported_type}")
                        content_parts.append(f"[Unsupported block: {unsupported_type}]")
                        continue
                    
                    # 1. Извлекаем текст из текущего блока, если он есть
                    block_content = ""
                    if b_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item", "to_do", "quote", "callout", "code", "toggle"]:
                        rich_text = block.get(b_type, {}).get("rich_text", [])
                        block_content = "".join([t.get("plain_text", "") for t in rich_text])
                        
                        if block_content:
                            if b_type.startswith("heading"):
                                level = b_type.split("_")[1]
                                block_content = f"{'#' * int(level)} {block_content}"
                            elif b_type == "to_do":
                                checked = " [x] " if block["to_do"].get("checked") else " [ ] "
                                block_content = f"{checked}{block_content}"
                            elif b_type == "bulleted_list_item":
                                block_content = f"• {block_content}"
                            elif b_type == "numbered_list_item":
                                block_content = f"1. {block_content}"
                            elif b_type == "code":
                                language = block.get("code", {}).get("language", "")
                                block_content = f"```{language}\n{block_content}\n```"
                            
                            content_parts.append(block_content)

                    # 2. Если есть дети — буримся глубже (рекурсия)
                    # Это сработает для synced_block, column, toggle и т.д.
                    if has_children:
                        child_text = await self._get_block_text_recursive(block["id"], depth + 1)
                        if child_text:
                            content_parts.append(child_text)
                
                next_cursor = response.get("next_cursor")
                if not next_cursor:
                    break
                    
            return "\n".join(content_parts).strip()
            
        except Exception as e:
            logger.debug(f"Ошибка при рекурсивном чтении блока {block_id}: {e}")
            return ""

    async def get_latest_meeting_notes(self, page_id: str) -> tuple[str, str, str]:
        """
        Получает последнюю запись встречи.
        Автоматически определяет тип объекта (база данных или страница) и использует оптимальный метод.
        """
        logger.info(f"🔍 Поиск последней встречи: {page_id}...")
        
        # Проверяем тип объекта
        object_type = await self._check_object_type(page_id)
        
        if object_type == "database":
            logger.info("Обнаружена база данных, используем query с сортировкой (O(1))")
            return await self.get_latest_from_database(page_id)
        
        # Для страницы пробуем получить meeting-notes
        logger.info("Обнаружена страница, получаем meeting-notes...")
        
        # Метод 1: Веб-скрапинг для получения полного контента (включая transcription)
        block_id, title, content = await self._get_content_via_mcp(page_id)
        
        if content and len(content.strip()) >= 100:
            logger.info(f"✅ Встреча найдена через веб-скрапинг: '{title}' ({len(content)} символов)")
            return (block_id, title, content)
        
        # Метод 2: Стандартный Notion API (fallback для доступного контента)
        logger.info("Веб-скрапинг не вернул контент, используем стандартный Notion API...")
        
        try:
            # Используем оптимизированную пагинацию (skip logic)
            # Увеличиваем количество блоков, чтобы захватить больше контента
            last_blocks = await self._get_last_blocks_optimized(page_id, last_n=20)
            
            if not last_blocks:
                logger.warning("Страница пуста")
                return ("", "", "")
            
            # Извлекаем текст из последних блоков рекурсивно
            content_parts = []
            transcription_blocks_found = 0
            
            for block in last_blocks:
                block_id_inner = block.get("id")
                block_type = block.get("type")
                
                # Пропускаем unsupported блоки, но считаем их
                if block_type == "unsupported":
                    transcription_blocks_found += 1
                    logger.debug(f"Пропущен unsupported блок #{transcription_blocks_found}")
                    continue
                
                # Извлекаем текст из блока
                try:
                    block_text = await self._get_block_text_recursive(block_id_inner, depth=0)
                    if block_text and block_text != "[Transcription блок - не поддерживается через API]":
                        content_parts.append(block_text)
                except Exception as block_error:
                    # Если ошибка связана с transcription, просто пропускаем
                    error_str = str(block_error).lower()
                    if "transcription" in error_str or "not supported" in error_str:
                        transcription_blocks_found += 1
                        logger.debug(f"Пропущен transcription блок: {block_error}")
                    else:
                        logger.debug(f"Ошибка при получении блока {block_id_inner}: {block_error}")
            
            content = "\n\n".join(content_parts)
            
            # Если нашли transcription блоки, но контент пустой, пробуем получить хотя бы заголовок
            # И пробуем получить summary через свойства страницы или другие методы
            if transcription_blocks_found > 0 and not content:
                logger.warning(f"Обнаружено {transcription_blocks_found} transcription блоков, но контент недоступен через API")
                
                # Пробуем получить информацию о странице и свойства, которые могут содержать summary
                try:
                    page = await self.client.pages.retrieve(page_id)
                    title = "Встреча"
                    summary_from_properties = None
                    
                    if "properties" in page:
                        for prop_name, prop_val in page["properties"].items():
                            prop_type = prop_val.get("type")
                            
                            # Заголовок
                            if prop_type == "title":
                                title_parts = prop_val.get("title", [])
                                if title_parts:
                                    title = title_parts[0].get("plain_text", "Встреча")
                            
                            # Ищем свойства, которые могут содержать summary/notes/transcript
                            if prop_type in ["rich_text", "text"]:
                                rich_text = prop_val.get(prop_type, [])
                                if rich_text:
                                    text = "".join([rt.get("plain_text", "") for rt in rich_text])
                                    # Если название свойства содержит summary/notes/transcript, сохраняем
                                    if text and len(text) > 100:
                                        prop_name_lower = prop_name.lower()
                                        if any(kw in prop_name_lower for kw in ["summary", "notes", "meeting", "transcript", "итоги", "резюме", "саммари"]):
                                            if not summary_from_properties:
                                                summary_from_properties = f"## {prop_name}\n{text}"
                                            else:
                                                summary_from_properties += f"\n\n## {prop_name}\n{text}"
                            
                            # Также проверяем все свойства с длинным текстом (может быть summary)
                            if prop_type in ["rich_text", "text"]:
                                rich_text = prop_val.get(prop_type, [])
                                if rich_text:
                                    text = "".join([rt.get("plain_text", "") for rt in rich_text])
                                    # Если текст длинный (более 200 символов), возможно это summary
                                    if text and len(text) > 200 and not summary_from_properties:
                                        # Проверяем, что это не просто заголовок или короткий текст
                                        if len(text.split()) > 30:  # Более 30 слов
                                            summary_from_properties = f"## {prop_name}\n{text}"
                    
                    # Если нашли summary в свойствах, используем его
                    if summary_from_properties:
                        content = summary_from_properties
                        logger.info(f"✅ Найден summary в свойствах страницы: {len(content)} символов")
                        return (page_id, title, content)
                    else:
                        # Если summary не найден, возвращаем сообщение об ошибке
                        return (page_id, title, f"[Обнаружено {transcription_blocks_found} transcription блоков, но они недоступны через стандартный Notion API. Требуется MCP с notion-fetch для получения meeting-notes.]")
                except Exception:
                    pass
            
            if content and len(content.strip()) >= 50:
                # Извлекаем заголовок из первого блока
                title = "Встреча"
                for block in last_blocks:
                    block_type = block.get("type")
                    if block_type.startswith("heading"):
                        rich_text = block.get(block_type, {}).get("rich_text", [])
                        if rich_text:
                            title = rich_text[0].get("plain_text", "Встреча")
                            break
                
                logger.info(f"✅ Получен контент через API: '{title}' ({len(content)} символов, пропущено transcription: {transcription_blocks_found})")
                return (page_id, title, content)
            else:
                logger.warning(f"Контент слишком короткий: {len(content) if content else 0} символов (пропущено transcription: {transcription_blocks_found})")
                return ("", "", "")
            
        except Exception as e:
            logger.error(f"Ошибка при получении контента страницы {page_id}: {e}")
            return ("", "", "")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def update_page_properties(
        self,
        page_id: str,
        properties: Dict[str, Any]
    ) -> None:
        """
        Обновляет свойства страницы Notion с ретраями.
        
        Args:
            page_id: ID страницы
            properties: Словарь свойств для обновления
        """
        try:
            await self.client.pages.update(page_id, properties=properties)
            logger.info(f"Обновлены свойства страницы {page_id}")
        except Exception as e:
            logger.error(f"Ошибка при обновлении свойств страницы {page_id}: {e}")
            raise

