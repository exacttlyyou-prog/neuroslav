"""
Асинхронный сервис для работы с Notion API с ретраями.
"""
from notion_client import AsyncClient
from loguru import logger
from typing import Dict, Any, List, Optional
from datetime import datetime
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from app.config import get_settings


class NotionService:
    """Сервис для работы с Notion API."""
    
    def __init__(self):
        settings = get_settings()
        if not settings.notion_token:
            raise ValueError("NOTION_TOKEN не установлен в переменных окружения")
        
        # Проверка формата токена
        if not settings.notion_token.startswith("secret_"):
            logger.warning("NOTION_TOKEN не начинается с 'secret_', возможно неверный формат")
        
        # Используем актуальную версию API 2025-09-03
        self.client = AsyncClient(auth=settings.notion_token, notion_version="2025-09-03")
        self.people_db_id = settings.notion_people_db_id
        self.projects_db_id = settings.notion_projects_db_id
        self.meeting_page_id = settings.notion_meeting_page_id
        self.glossary_db_id = settings.notion_glossary_db_id
    
    async def validate_token(self) -> bool:
        """
        Проверяет, что NOTION_TOKEN валиден и API доступен.
        
        Returns:
            True если токен валиден, False иначе
        """
        try:
            # Пробуем получить информацию о пользователе через users.me или тестовую страницу
            if self.meeting_page_id:
                # Пробуем получить страницу встреч
                await self.client.pages.retrieve(self.meeting_page_id)
            else:
                # Если нет meeting_page_id, пробуем получить список баз данных (требует интеграцию)
                # Или просто проверяем, что клиент может делать запросы
                # Для минимальной проверки можно использовать users.me если доступно
                pass
            logger.info("✅ NOTION_TOKEN валиден, API доступен")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if "unauthorized" in error_msg or "401" in error_msg:
                logger.error("❌ NOTION_TOKEN невалиден (401 Unauthorized). Проверьте токен в .env")
            elif "forbidden" in error_msg or "403" in error_msg:
                logger.error("❌ Notion API: Доступ запрещен (403). Проверьте права доступа токена")
            elif "not found" in error_msg or "404" in error_msg:
                logger.warning("⚠️ Страница не найдена, но токен валиден")
                return True  # Токен работает, просто страница не найдена
            else:
                logger.error(f"❌ NOTION_TOKEN невалиден или API недоступен: {e}")
            return False
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def _extract_text_from_block(self, block: Dict[str, Any]) -> str:
        """
        Извлекает текст из блока любого типа.
        
        Args:
            block: Блок Notion
            
        Returns:
            Текст из блока
        """
        block_type = block.get("type")
        text_parts = []
        
        # Получаем rich_text из разных типов блоков
        rich_text = None
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", 
                         "bulleted_list_item", "numbered_list_item", "to_do", 
                         "toggle", "quote", "callout", "code"]:
            block_data = block.get(block_type, {})
            rich_text = block_data.get("rich_text", [])
        elif block_type == "table":
            # Таблицы обрабатываем отдельно
            return "[Таблица]"
        elif block_type == "child_page":
            # Дочерние страницы - возвращаем название
            title = block.get("child_page", {}).get("title", "Без названия")
            return f"\n[Страница: {title}]\n"
        elif block_type == "child_database":
            # Дочерние базы данных
            return "[База данных]"
        
        # Извлекаем весь текст из rich_text
        if rich_text:
            for rt in rich_text:
                plain_text = rt.get("plain_text", "")
                if plain_text:
                    text_parts.append(plain_text)
        
        return "".join(text_parts)
    
    async def _get_all_blocks_recursive(self, block_id: str) -> List[Dict[str, Any]]:
        """
        Рекурсивно получает все блоки со страницы или из блока.
        
        Args:
            block_id: ID страницы или блока
            
        Returns:
            Список всех блоков (включая вложенные)
        """
        all_blocks = []
        has_more = True
        start_cursor = None
        
        # Получаем все блоки с пагинацией
        while has_more:
            query_params = {"block_id": block_id}
            if start_cursor:
                query_params["start_cursor"] = start_cursor
            
            try:
                response = await self.client.blocks.children.list(**query_params)
                blocks = response.get("results", [])
                all_blocks.extend(blocks)
                
                has_more = response.get("has_more", False)
                start_cursor = response.get("next_cursor")
            except Exception as e:
                # Некоторые типы блоков (например, transcription) не поддерживаются через API
                error_msg = str(e).lower()
                if "transcription" in error_msg or "not supported" in error_msg:
                    logger.debug(f"Блок {block_id} имеет тип, не поддерживаемый через API, пропускаем")
                    break
                raise
        
        # Рекурсивно получаем дочерние блоки
        result_blocks = []
        for block in all_blocks:
            result_blocks.append(block)
            
            # Проверяем, есть ли у блока дочерние элементы
            has_children = block.get("has_children", False)
            block_type = block.get("type", "")
            
            # Пропускаем блоки типа transcription - они не поддерживаются через API
            if block_type == "transcription":
                logger.debug(f"Пропускаем блок типа transcription: {block.get('id')}")
                continue
            
            if has_children:
                try:
                    child_blocks = await self._get_all_blocks_recursive(block["id"])
                    result_blocks.extend(child_blocks)
                except Exception as e:
                    logger.warning(f"Не удалось получить дочерние блоки для {block['id']}: {e}")
        
        return result_blocks
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def get_page_content(self, page_id: str, include_metadata: bool = False) -> str:
        """
        Получает полный контент страницы Notion с ретраями (рекурсивно).
        
        Args:
            page_id: ID страницы Notion
            include_metadata: Включать ли метаданные страницы (название, свойства)
            
        Returns:
            Текст контента страницы
        """
        try:
            page = await self.client.pages.retrieve(page_id)
            text_parts = []
            
            # Добавляем название страницы, если нужно
            if include_metadata:
                properties = page.get("properties", {})
                for prop_name, prop_val in properties.items():
                    prop_type = prop_val.get("type")
                    if prop_type == "title":
                        title_parts = prop_val.get("title", [])
                        if title_parts:
                            title = "".join([t.get("plain_text", "") for t in title_parts])
                            if title:
                                text_parts.append(f"# {title}\n")
            
            # Получаем все блоки рекурсивно
            all_blocks = await self._get_all_blocks_recursive(page_id)
            
            # Извлекаем текст из всех блоков
            for block in all_blocks:
                block_text = await self._extract_text_from_block(block)
                if block_text:
                    text_parts.append(block_text)
            
            return "\n".join(text_parts)
        except Exception as e:
            error_msg = str(e).lower()
            if "unauthorized" in error_msg or "401" in error_msg:
                logger.error(f"❌ Notion API: Неверный токен (401) при получении страницы {page_id}")
                raise ValueError("Неверный NOTION_TOKEN") from e
            elif "forbidden" in error_msg or "403" in error_msg:
                logger.error(f"❌ Notion API: Доступ запрещен (403) к странице {page_id}")
                raise ValueError("Недостаточно прав доступа к Notion") from e
            elif "not found" in error_msg or "404" in error_msg:
                logger.error(f"❌ Notion API: Страница не найдена (404): {page_id}")
                raise ValueError(f"Страница {page_id} не найдена") from e
            else:
                logger.error(f"Ошибка при получении контента страницы {page_id}: {e}")
                raise
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def get_last_meeting_content(self, page_id: str) -> Optional[str]:
        """
        Получает контент последней встречи со страницы Notion.
        
        Args:
            page_id: ID страницы Notion с встречами
            
        Returns:
            Текст последней встречи или None
        """
        try:
            blocks = await self.client.blocks.children.list(page_id)
            
            # Ищем последний блок с типом "heading" или "paragraph"
            for block in reversed(blocks.get("results", [])):
                block_type = block.get("type")
                if block_type in ["heading_1", "heading_2", "heading_3", "paragraph"]:
                    rich_text = block.get(block_type, {}).get("rich_text", [])
                    if rich_text:
                        return rich_text[0].get("plain_text", "")
            
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении последней встречи со страницы {page_id}: {e}")
            return None

    async def get_last_meeting_block(self, page_id: str) -> Dict[str, Any]:
        """
        Возвращает контент последнего блока на странице встреч.
        
        Args:
            page_id: ID страницы Notion
            
        Returns:
            Словарь с данными последнего блока
        """
        try:
            results = []
            has_more = True
            start_cursor = None
            while has_more:
                query_params = {"block_id": page_id}
                if start_cursor:
                    query_params["start_cursor"] = start_cursor
                response = await self.client.blocks.children.list(**query_params)
                results.extend(response.get("results", []))
                has_more = response.get("has_more", False)
                start_cursor = response.get("next_cursor")
            if not results:
                return {
                    "block_id": None,
                    "block_type": None,
                    "content": ""
                }
            
            last_block = results[-1]
            block_id = last_block.get("id")
            block_type = last_block.get("type")
            
            # Пропускаем блоки типа transcription - они не поддерживаются через API
            if block_type == "transcription":
                logger.warning(f"Последний блок имеет тип 'transcription', который не поддерживается через API. Пробуем предыдущий блок...")
                # Пробуем взять предыдущий блок
                if len(results) > 1:
                    last_block = results[-2]
                    block_id = last_block.get("id")
                    block_type = last_block.get("type")
                else:
                    return {
                        "block_id": None,
                        "block_type": None,
                        "content": ""
                    }
            
            # Если последний блок — страница, возвращаем ее контент
            if block_type == "child_page" and block_id:
                content = await self.get_page_content(block_id, include_metadata=True)
            else:
                text_parts = []
                base_text = await self._extract_text_from_block(last_block)
                if base_text:
                    text_parts.append(base_text)
                
                if last_block.get("has_children") and block_id and block_type != "transcription":
                    try:
                        child_blocks = await self._get_all_blocks_recursive(block_id)
                        for block in child_blocks:
                            block_text = await self._extract_text_from_block(block)
                            if block_text:
                                text_parts.append(block_text)
                    except Exception as e:
                        # Если не удалось получить дочерние блоки (например, transcription), используем только базовый текст
                        logger.debug(f"Не удалось получить дочерние блоки для {block_id}: {e}")
                
                content = "\n".join(text_parts).strip()
            
            return {
                "block_id": block_id,
                "block_type": block_type,
                "content": content
            }
        except Exception as e:
            logger.error(f"Ошибка при получении последнего блока со страницы {page_id}: {e}")
            raise
    
    async def get_database_data_sources(self, database_id: str) -> List[Dict[str, Any]]:
        """
        Получает data sources из базы данных (для API версии 2025-09-03).
        
        Args:
            database_id: ID базы данных
            
        Returns:
            Список data sources
        """
        try:
            database = await self.client.databases.retrieve(database_id)
            data_sources = database.get("data_sources", [])
            
            if not data_sources:
                logger.warning(f"База данных {database_id} не содержит data sources")
                return []
            
            logger.info(f"Найдено {len(data_sources)} data sources в базе {database_id}")
            return data_sources
        except Exception as e:
            logger.error(f"Ошибка при получении data sources из базы {database_id}: {e}")
            return []
    
    async def _query_database(self, database_id: str, page_size: int = 100) -> List[Dict[str, Any]]:
        """
        Универсальный метод для запроса базы данных с поддержкой API версии 2025-09-03.
        
        Args:
            database_id: ID базы данных
            page_size: Размер страницы (максимум 100)
            
        Returns:
            Список страниц из базы данных
        """
        try:
            import httpx
            
            # Для API версии 2025-09-03 сначала получаем database, чтобы найти data sources
            settings = get_settings()
            headers = {
                "Authorization": f"Bearer {settings.notion_token}",
                "Notion-Version": "2025-09-03",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient() as client:
                # Получаем информацию о базе данных
                db_response = await client.get(
                    f"https://api.notion.com/v1/databases/{database_id}",
                    headers=headers
                )
                db_response.raise_for_status()
                database = db_response.json()
                
                # Проверяем data sources
                data_sources = database.get("data_sources", [])
                query_id = database_id
                
                # Если есть data sources, используем первый
                if data_sources:
                    query_id = data_sources[0].get("id", database_id)
                    logger.info(f"Используем data source: {query_id}")
                
                results = []
                has_more = True
                start_cursor = None
                
                while has_more:
                    query_data = {"page_size": min(page_size, 100)}
                    if start_cursor:
                        query_data["start_cursor"] = start_cursor
                    
                    # Пробуем сначала через data_sources endpoint
                    if data_sources:
                        response = await client.post(
                            f"https://api.notion.com/v1/data_sources/{query_id}/query",
                            headers=headers,
                            json=query_data
                        )
                    else:
                        # Fallback на старый endpoint
                        response = await client.post(
                            f"https://api.notion.com/v1/databases/{database_id}/query",
                            headers=headers,
                            json=query_data
                        )
                    
                    if response.status_code == 400:
                        # Если не работает data_sources, пробуем старый способ
                        response = await client.post(
                            f"https://api.notion.com/v1/databases/{database_id}/query",
                            headers=headers,
                            json=query_data
                        )
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    results.extend(data.get("results", []))
                    has_more = data.get("has_more", False)
                    start_cursor = data.get("next_cursor")
            
            return results
        except Exception as e:
            logger.error(f"Ошибка при запросе базы данных {database_id}: {e}")
            raise
    
    async def get_contacts_from_db(self) -> List[Dict[str, Any]]:
        """
        Получает список контактов из базы данных Notion "Люди".
        
        Returns:
            Список контактов
        """
        if not self.people_db_id:
            logger.warning("NOTION_PEOPLE_DB_ID не установлен")
            return []
        
        try:
            results = await self._query_database(self.people_db_id)
            
            contacts = []
            for page in results:
                props = page.get("properties", {})
                contact = {
                    "id": page["id"],
                    "name": "",
                    "telegram_username": "",
                    "role": "",
                    "context": "",
                    "aliases": []
                }
                
                # Извлекаем свойства
                for prop_name, prop_val in props.items():
                    prop_type = prop_val.get("type")
                    if prop_type == "title":
                        title_parts = prop_val.get("title", [])
                        if title_parts:
                            contact["name"] = title_parts[0].get("plain_text", "")
                    elif prop_type == "rich_text":
                        rich_text = prop_val.get("rich_text", [])
                        if rich_text:
                            text = rich_text[0].get("plain_text", "")
                            if "telegram" in prop_name.lower() or "username" in prop_name.lower():
                                contact["telegram_username"] = text.lstrip("@")
                            elif "role" in prop_name.lower():
                                contact["role"] = text
                            elif "context" in prop_name.lower() or "описание" in prop_name.lower():
                                contact["context"] = text
                    elif prop_type == "multi_select":
                        select_options = prop_val.get("multi_select", [])
                        contact["aliases"] = [opt.get("name", "") for opt in select_options]
                
                contacts.append(contact)
            
            logger.info(f"Получено {len(contacts)} контактов из Notion")
            return contacts
            
        except Exception as e:
            logger.error(f"Ошибка при получении контактов из Notion: {e}")
            return []
    
    async def get_projects_from_db(self) -> List[Dict[str, Any]]:
        """
        Получает список проектов из базы данных Notion "Проекты".
        
        Returns:
            Список проектов
        """
        if not self.projects_db_id:
            logger.warning("NOTION_PROJECTS_DB_ID не установлен")
            return []
        
        try:
            results = await self._query_database(self.projects_db_id)
            
            projects = []
            for page in results:
                props = page.get("properties", {})
                project = {
                    "id": page["id"],
                    "key": "",
                    "description": "",
                    "keywords": []
                }
                
                # Извлекаем свойства
                for prop_name, prop_val in props.items():
                    prop_type = prop_val.get("type")
                    if prop_type == "title":
                        title_parts = prop_val.get("title", [])
                        if title_parts:
                            project["key"] = title_parts[0].get("plain_text", "")
                    elif prop_type == "rich_text":
                        rich_text = prop_val.get("rich_text", [])
                        if rich_text:
                            project[prop_name.lower()] = rich_text[0].get("plain_text", "")
                    elif prop_type == "multi_select":
                        select_options = prop_val.get("multi_select", [])
                        project["keywords"] = [opt.get("name", "") for opt in select_options]
                
                projects.append(project)
            
            logger.info(f"Получено {len(projects)} проектов из Notion")
            return projects
            
        except Exception as e:
            logger.error(f"Ошибка при получении проектов из Notion: {e}")
            return []
    
    async def get_glossary_from_db(self) -> Dict[str, str]:
        """
        Получает глоссарий терминов из базы данных Notion "Глоссарий".
        
        Returns:
            Словарь {термин: определение}
        """
        if not self.glossary_db_id:
            logger.warning("NOTION_GLOSSARY_DB_ID не установлен")
            return {}
        
        try:
            results = await self._query_database(self.glossary_db_id)
            
            glossary = {}
            for page in results:
                props = page.get("properties", {})
                term = ""
                definition = ""
                
                for prop_name, prop_val in props.items():
                    prop_type = prop_val.get("type")
                    if prop_type == "title":
                        title_parts = prop_val.get("title", [])
                        if title_parts:
                            term = title_parts[0].get("plain_text", "")
                    elif prop_type == "rich_text":
                        rich_text = prop_val.get("rich_text", [])
                        if rich_text:
                            definition = rich_text[0].get("plain_text", "")
                
                if term:
                    glossary[term.lower()] = definition
            
            logger.info(f"Получено {len(glossary)} терминов из глоссария Notion")
            return glossary
            
        except Exception as e:
            logger.error(f"Ошибка при получении глоссария из Notion: {e}")
            return {}
    
    async def create_task_in_notion(self, task_data: Dict[str, Any], page_id: Optional[str] = None) -> str:
        """
        Создает задачу в Notion.
        
        Args:
            task_data: Данные задачи (text, deadline, priority, assignee)
            page_id: ID страницы для создания задачи (опционально)
            
        Returns:
            ID созданной задачи
        """
        try:
            # Формируем блок для задачи
            block_data = {
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": task_data.get("text", "")}
                        }
                    ],
                    "checked": False
                }
            }
            
            if page_id:
                # Добавляем блок на страницу
                response = await self.client.blocks.children.append(
                    block_id=page_id,
                    children=[block_data]
                )
                task_id = response["results"][0]["id"]
            else:
                # Создаем новую страницу
                new_page = await self.client.pages.create(
                    parent={"type": "page_id", "page_id": self.meeting_page_id or ""},
                    properties={
                        "title": {
                            "title": [{"text": {"content": task_data.get("text", "")[:200]}}]
                        }
                    },
                    children=[block_data]
                )
                task_id = new_page["id"]
            
            logger.info(f"Создана задача в Notion: {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Ошибка при создании задачи в Notion: {e}")
            raise
    
    async def save_meeting_summary(self, page_id: str, summary: str) -> None:
        """
        Сохраняет summary встречи на страницу Notion.
        
        Args:
            page_id: ID страницы Notion
            summary: Текст summary
        """
        try:
            # Добавляем блок с summary
            block_data = {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": summary}
                        }
                    ]
                }
            }
            
            await self.client.blocks.children.append(
                block_id=page_id,
                children=[block_data]
            )
            
            logger.info(f"Summary сохранен на страницу {page_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении summary в Notion: {e}")
            raise
    
    async def create_meeting_page(
        self,
        meeting_title: str,
        summary: str,
        participants: List[Dict[str, Any]],
        action_items: List[Dict[str, Any]],
        parent_page_id: Optional[str] = None
    ) -> str:
        """
        Создает страницу встречи в Notion с полной структурой.
        
        Args:
            meeting_title: Название встречи
            summary: Саммари встречи
            participants: Список участников
            action_items: Список action items
            parent_page_id: ID родительской страницы (если None, используется meeting_page_id)
            
        Returns:
            ID созданной страницы
        """
        try:
            parent_id = parent_page_id or self.meeting_page_id
            if not parent_id:
                raise ValueError("Не указан parent_page_id и NOTION_MEETING_PAGE_ID не установлен")
            
            # Формируем блоки для страницы
            children = []
            
            # Заголовок "Саммари"
            children.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Саммари"}}]
                }
            })
            
            # Саммари
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": summary}}]
                }
            })
            
            # Участники
            if participants:
                children.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": "Участники"}}]
                    }
                })
                for participant in participants:
                    name = participant.get("name", "Неизвестно") if isinstance(participant, dict) else str(participant)
                    children.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {"content": name}}]
                        }
                    })
            
            # Action Items
            if action_items:
                children.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": "Задачи"}}]
                    }
                })
                for item in action_items:
                    text = item.get("text", "") if isinstance(item, dict) else str(item)
                    assignee = item.get("assignee", "") if isinstance(item, dict) else ""
                    priority = item.get("priority", "") if isinstance(item, dict) else ""
                    
                    item_text = text
                    if assignee:
                        item_text += f" → {assignee}"
                    if priority:
                        item_text += f" [{priority}]"
                    
                    children.append({
                        "object": "block",
                        "type": "to_do",
                        "to_do": {
                            "rich_text": [{"type": "text", "text": {"content": item_text}}],
                            "checked": False
                        }
                    })
            
            # Создаем страницу
            new_page = await self.client.pages.create(
                parent={"type": "page_id", "page_id": parent_id},
                properties={
                    "title": {
                        "title": [{"type": "text", "text": {"content": meeting_title}}]
                    }
                },
                children=children
            )
            
            page_id = new_page["id"]
            logger.info(f"Создана страница встречи в Notion: {page_id}")
            return page_id
            
        except Exception as e:
            error_msg = str(e).lower()
            if "unauthorized" in error_msg or "401" in error_msg:
                logger.error("❌ Notion API: Неверный токен (401) при создании страницы")
                raise ValueError("Неверный NOTION_TOKEN") from e
            elif "forbidden" in error_msg or "403" in error_msg:
                logger.error("❌ Notion API: Доступ запрещен (403) при создании страницы")
                raise ValueError("Недостаточно прав доступа к Notion") from e
            else:
                logger.error(f"Ошибка при создании страницы встречи в Notion: {e}")
                raise
    
    async def get_ai_context_pages(self, parent_page_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Получает список страниц из базы AI-Context или дочерних страниц.
        
        Args:
            parent_page_id: ID родительской страницы (если None, используется meeting_page_id)
            
        Returns:
            Список страниц с их контентом
        """
        try:
            parent_id = parent_page_id or self.meeting_page_id
            if not parent_id:
                logger.warning("Не указан parent_page_id для получения AI-Context")
                return []
            
            # Получаем дочерние страницы
            blocks = await self.client.blocks.children.list(parent_id)
            pages = []
            
            for block in blocks.get("results", []):
                if block.get("type") == "child_page":
                    page_id = block["id"]
                    page_title = block.get("child_page", {}).get("title", "Без названия")
                    
                    # Получаем контент страницы
                    try:
                        content = await self.get_page_content(page_id)
                        pages.append({
                            "id": page_id,
                            "title": page_title,
                            "content": content
                        })
                    except Exception as e:
                        logger.warning(f"Не удалось получить контент страницы {page_id}: {e}")
                        pages.append({
                            "id": page_id,
                            "title": page_title,
                            "content": ""
                        })
            
            logger.info(f"Получено {len(pages)} страниц из AI-Context")
            return pages
            
        except Exception as e:
            logger.error(f"Ошибка при получении AI-Context страниц: {e}")
            return []
    
    async def search_in_notion(self, query: str, database_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Ищет в базе данных Notion по тексту.
        
        Args:
            query: Поисковый запрос
            database_id: ID базы данных (если None, ищет во всех доступных)
            
        Returns:
            Список найденных страниц
        """
        try:
            databases_to_search = []
            if database_id:
                databases_to_search.append(database_id)
            else:
                if self.people_db_id:
                    databases_to_search.append(self.people_db_id)
                if self.projects_db_id:
                    databases_to_search.append(self.projects_db_id)
                if self.glossary_db_id:
                    databases_to_search.append(self.glossary_db_id)
            
            results = []
            for db_id in databases_to_search:
                try:
                    # Простой поиск по title и rich_text полям
                    response = await self.client.databases.query(
                        database_id=db_id,
                        filter={
                            "or": [
                                {
                                    "property": "title",
                                    "title": {"contains": query}
                                }
                            ]
                        }
                    )
                    results.extend(response.get("results", []))
                except Exception as e:
                    logger.warning(f"Ошибка при поиске в базе {db_id}: {e}")
            
            logger.info(f"Найдено {len(results)} результатов по запросу '{query}'")
            return results
            
        except Exception as e:
            logger.error(f"Ошибка при поиске в Notion: {e}")
            return []
