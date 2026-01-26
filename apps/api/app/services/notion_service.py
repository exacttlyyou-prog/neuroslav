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
        if not settings.notion_token.startswith("secret_") and not settings.notion_token.startswith("ntn_"):
            logger.warning("NOTION_TOKEN не начинается с 'secret_' или 'ntn_', возможно неверный формат")
        
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
    
    async def ensure_required_databases(self) -> Dict[str, Any]:
        """
        Проверяет наличие и при необходимости создаёт требуемые базы данных.
        
        Returns:
            Статус инициализации баз данных
        """
        status = {
            "ai_context_page": None,
            "people_db": None,
            "projects_db": None,
            "meetings_db": None,
            "tasks_db": None,
            "daily_reports_db": None,
            "errors": []
        }
        
        try:
            # 1. Убеждаемся что AI-Context страница существует
            if not self.meeting_page_id:
                status["errors"].append("NOTION_MEETING_PAGE_ID не установлен")
                logger.error("❌ NOTION_MEETING_PAGE_ID не установлен в конфигурации")
                return status
            
            try:
                ai_context_page = await self.client.pages.retrieve(self.meeting_page_id)
                status["ai_context_page"] = "exists"
                logger.info("✅ AI-Context страница найдена")
            except Exception as e:
                status["errors"].append(f"AI-Context страница недоступна: {str(e)}")
                logger.error(f"❌ AI-Context страница недоступна: {e}")
                return status
            
            # 2. Проверяем/создаем базу данных People
            if not self.people_db_id:
                logger.info("📊 База данных People не настроена, создаю...")
                try:
                    people_db = await self._create_people_database()
                    status["people_db"] = "created"
                    logger.info("✅ База данных People создана")
                except Exception as e:
                    status["errors"].append(f"Не удалось создать базу People: {str(e)}")
                    logger.error(f"❌ Ошибка создания базы People: {e}")
            else:
                try:
                    await self.client.databases.retrieve(self.people_db_id)
                    status["people_db"] = "exists"
                    logger.info("✅ База данных People найдена")
                except Exception as e:
                    status["errors"].append(f"База People недоступна: {str(e)}")
                    logger.error(f"❌ База данных People недоступна: {e}")
            
            # 3. Проверяем/создаем базу данных Projects
            if not self.projects_db_id:
                logger.info("📊 База данных Projects не настроена, создаю...")
                try:
                    projects_db = await self._create_projects_database()
                    status["projects_db"] = "created"
                    logger.info("✅ База данных Projects создана")
                except Exception as e:
                    status["errors"].append(f"Не удалось создать базу Projects: {str(e)}")
                    logger.error(f"❌ Ошибка создания базы Projects: {e}")
            else:
                try:
                    await self.client.databases.retrieve(self.projects_db_id)
                    status["projects_db"] = "exists"
                    logger.info("✅ База данных Projects найдена")
                except Exception as e:
                    status["errors"].append(f"База Projects недоступна: {str(e)}")
                    logger.error(f"❌ База данных Projects недоступна: {e}")
            
            # 4. Создаем базу данных Meetings (всегда создаем новую)
            logger.info("📊 Создаю базу данных Meetings...")
            try:
                meetings_db = await self._create_meetings_database()
                status["meetings_db"] = "created"
                logger.info("✅ База данных Meetings создана")
            except Exception as e:
                status["errors"].append(f"Не удалось создать базу Meetings: {str(e)}")
                logger.error(f"❌ Ошибка создания базы Meetings: {e}")
            
            # 5. Создаем базу данных Tasks (всегда создаем новую)  
            logger.info("📊 Создаю базу данных Tasks...")
            try:
                tasks_db = await self._create_tasks_database()
                status["tasks_db"] = "created"
                logger.info("✅ База данных Tasks создана")
            except Exception as e:
                status["errors"].append(f"Не удалось создать базу Tasks: {str(e)}")
                logger.error(f"❌ Ошибка создания базы Tasks: {e}")
            
            # 6. Проверяем/создаем базу данных Daily Reports
            logger.info("📊 Проверка базы данных Daily Reports...")
            try:
                db_id = await self.get_or_create_daily_reports_database()
                status["daily_reports_db"] = "exists" if db_id else "created"
                logger.info("✅ База данных Daily Reports готова")
            except Exception as e:
                status["errors"].append(f"Не удалось инициализировать базу Daily Reports: {str(e)}")
                logger.error(f"❌ Ошибка инициализации базы Daily Reports: {e}")
            
            return status
            
        except Exception as e:
            status["errors"].append(f"Критическая ошибка инициализации: {str(e)}")
            logger.error(f"❌ Критическая ошибка при проверке баз данных: {e}")
            return status
    
    async def _create_people_database(self) -> Dict[str, Any]:
        """Создает базу данных People в Notion."""
        database_properties = {
            "Name": {"title": {}},
            "Telegram Username": {"rich_text": {}},
            "Role": {"select": {"options": [
                {"name": "Developer", "color": "blue"},
                {"name": "Manager", "color": "green"},
                {"name": "Designer", "color": "purple"},
                {"name": "Analyst", "color": "orange"},
                {"name": "Other", "color": "gray"}
            ]}},
            "Email": {"email": {}},
            "Aliases": {"multi_select": {"options": []}},
            "Telegram Chat ID": {"rich_text": {}}
        }
        
        return await self.client.databases.create(
            parent={"type": "page_id", "page_id": self.meeting_page_id},
            title=[{"type": "text", "text": {"content": "People Database"}}],
            properties=database_properties
        )
    
    async def _create_projects_database(self) -> Dict[str, Any]:
        """Создает базу данных Projects в Notion."""
        database_properties = {
            "Name": {"title": {}},
            "Key": {"rich_text": {}},
            "Description": {"rich_text": {}},
            "Status": {"select": {"options": [
                {"name": "Active", "color": "green"},
                {"name": "Paused", "color": "yellow"},
                {"name": "Completed", "color": "blue"},
                {"name": "Cancelled", "color": "red"}
            ]}},
            "Keywords": {"multi_select": {"options": []}}
        }
        
        return await self.client.databases.create(
            parent={"type": "page_id", "page_id": self.meeting_page_id},
            title=[{"type": "text", "text": {"content": "Projects Database"}}],
            properties=database_properties
        )
    
    async def _create_meetings_database(self) -> Dict[str, Any]:
        """Создает базу данных Meetings в Notion."""
        database_properties = {
            "Title": {"title": {}},
            "Date": {"date": {}},
            "Participants": {"multi_select": {"options": []}},
            "Projects": {"multi_select": {"options": []}},
            "Status": {"select": {"options": [
                {"name": "Draft", "color": "gray"},
                {"name": "Approved", "color": "green"},
                {"name": "Sent", "color": "blue"}
            ]}},
            "Summary": {"rich_text": {}},
            "Key Decisions": {"rich_text": {}},
            "Action Items": {"rich_text": {}},
            "Insights": {"rich_text": {}},
            "Next Steps": {"rich_text": {}},
            "Meeting ID": {"rich_text": {}}
        }
        
        return await self.client.databases.create(
            parent={"type": "page_id", "page_id": self.meeting_page_id},
            title=[{"type": "text", "text": {"content": "Meetings Database"}}],
            properties=database_properties
        )
    
    async def _create_tasks_database(self) -> Dict[str, Any]:
        """Создает базу данных Tasks в Notion."""
        database_properties = {
            "Title": {"title": {}},
            "Assignee": {"select": {"options": []}},
            "Project": {"select": {"options": []}},
            "Priority": {"select": {"options": [
                {"name": "High", "color": "red"},
                {"name": "Medium", "color": "yellow"},
                {"name": "Low", "color": "green"}
            ]}},
            "Status": {"select": {"options": [
                {"name": "Todo", "color": "gray"},
                {"name": "In Progress", "color": "blue"},
                {"name": "Done", "color": "green"},
                {"name": "Cancelled", "color": "red"}
            ]}},
            "Due Date": {"date": {}},
            "Description": {"rich_text": {}},
            "Meeting ID": {"rich_text": {}},
            "Created": {"created_time": {}}
        }
        
        return await self.client.databases.create(
            parent={"type": "page_id", "page_id": self.meeting_page_id},
            title=[{"type": "text", "text": {"content": "Tasks Database"}}],
            properties=database_properties
        )
    
    async def get_or_create_daily_reports_database(self, parent_page_id: Optional[str] = None) -> str:
        """
        Получает или создает базу данных Daily Reports в Notion.
        
        Args:
            parent_page_id: ID родительской страницы (если None, используется meeting_page_id)
            
        Returns:
            ID базы данных Daily Reports
        """
        try:
            parent_id = parent_page_id or self.meeting_page_id
            if not parent_id:
                raise ValueError("Не указан parent_page_id и NOTION_MEETING_PAGE_ID не установлен")
            
            # Проверяем, есть ли уже база Daily Reports среди дочерних страниц
            blocks = await self.client.blocks.children.list(parent_id)
            for block in blocks.get("results", []):
                if block.get("type") == "child_database":
                    db_id = block["id"]
                    # Проверяем название базы
                    try:
                        db_info = await self.client.databases.retrieve(db_id)
                        db_title = ""
                        if db_info.get("title"):
                            title_parts = db_info["title"]
                            if isinstance(title_parts, list) and title_parts:
                                db_title = title_parts[0].get("plain_text", "")
                        
                        if "daily" in db_title.lower() or "отчет" in db_title.lower() or "report" in db_title.lower():
                            logger.info(f"✅ Найдена существующая база Daily Reports: {db_id}")
                            return db_id
                    except Exception as e:
                        logger.debug(f"Ошибка при проверке базы {db_id}: {e}")
                        continue
            
            # Если не найдена, создаем новую
            logger.info("📊 Создаю базу данных Daily Reports...")
            
            database_properties = {
                "Name": {"title": {}},
                "Date": {"date": {}},
                "Response": {"rich_text": {}},
                "Status": {"select": {"options": [
                    {"name": "Выполнено", "color": "green"},
                    {"name": "В процессе", "color": "yellow"},
                    {"name": "Проблема", "color": "red"},
                    {"name": "Не ответил", "color": "gray"}
                ]}},
                "Contact": {"rich_text": {}},
                "Tasks Mentioned": {"rich_text": {}},
                "Created": {"created_time": {}}
            }
            
            new_db = await self.client.databases.create(
                parent={"type": "page_id", "page_id": parent_id},
                title=[{"type": "text", "text": {"content": "Daily Reports"}}],
                properties=database_properties
            )
            
            db_id = new_db["id"]
            logger.info(f"✅ База данных Daily Reports создана: {db_id}")
            return db_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении/создании базы Daily Reports: {e}")
            raise
    
    async def save_daily_report(
        self,
        contact_name: str,
        response_text: str,
        checkin_date: datetime,
        status: str = "Выполнено",
        tasks_mentioned: Optional[List[str]] = None,
        parent_page_id: Optional[str] = None
    ) -> str:
        """
        Сохраняет daily report в базу данных Notion Daily Reports.
        
        Args:
            contact_name: Имя контакта
            response_text: Текст ответа
            checkin_date: Дата опроса
            status: Статус (Выполнено, В процессе, Проблема)
            tasks_mentioned: Список упомянутых задач
            parent_page_id: ID родительской страницы
            
        Returns:
            ID созданной записи
        """
        try:
            # Получаем или создаем базу Daily Reports
            db_id = await self.get_or_create_daily_reports_database(parent_page_id)
            
            # Формируем свойства для записи
            properties = {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": f"{contact_name} - {checkin_date.strftime('%Y-%m-%d')}"
                            }
                        }
                    ]
                },
                "Date": {
                    "date": {
                        "start": checkin_date.strftime('%Y-%m-%d')
                    }
                },
                "Response": {
                    "rich_text": [
                        {
                            "text": {
                                "content": response_text[:2000]  # Ограничение Notion
                            }
                        }
                    ]
                },
                "Status": {
                    "select": {
                        "name": status
                    }
                },
                "Contact": {
                    "rich_text": [
                        {
                            "text": {
                                "content": contact_name
                            }
                        }
                    ]
                }
            }
            
            if tasks_mentioned:
                tasks_text = ", ".join(tasks_mentioned[:10])  # Максимум 10 задач
                properties["Tasks Mentioned"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": tasks_text[:2000]
                            }
                        }
                    ]
                }
            
            # Создаем запись в базе данных
            created_page = await self.client.pages.create(
                parent={"database_id": db_id},
                properties=properties
            )
            
            page_id = created_page["id"]
            logger.info(f"✅ Daily report сохранен в Notion: {page_id}")
            return page_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении daily report в Notion: {e}")
            raise
    
    async def create_meeting_in_db(
        self,
        meeting_id: str,
        title: str,
        summary: str,
        participants: List[Dict[str, Any]],
        action_items: List[Dict[str, Any]],
        key_decisions: List[Dict[str, Any]] = None,
        insights: List[str] = None,
        next_steps: List[str] = None,
        projects: List[Dict[str, Any]] = None,
        meetings_db_id: str = None
    ) -> Dict[str, Any]:
        """
        Создает запись о встрече в базе данных Meetings в Notion.
        
        Args:
            meeting_id: ID встречи из системы
            title: Заголовок встречи
            summary: Саммари встречи  
            participants: Список участников
            action_items: Список задач
            key_decisions: Ключевые решения
            insights: Инсайты
            next_steps: Следующие шаги
            projects: Связанные проекты
            meetings_db_id: ID базы данных Meetings (если не указан, ищем автоматически)
            
        Returns:
            Созданная страница встречи
        """
        try:
            # Если не передан meetings_db_id, пробуем найти автоматически
            if not meetings_db_id:
                # Ищем базу данных "Meetings Database" среди дочерних страниц AI-Context
                children = await self.client.blocks.children.list(self.meeting_page_id)
                for child in children.get("results", []):
                    if child.get("type") == "child_database":
                        # Получаем информацию о базе данных
                        db_info = await self.client.databases.retrieve(child["id"])
                        db_title = ""
                        if db_info.get("title"):
                            db_title = "".join([t.get("plain_text", "") for t in db_info["title"]])
                        
                        if "meetings" in db_title.lower():
                            meetings_db_id = child["id"]
                            break
                
                if not meetings_db_id:
                    raise ValueError("База данных Meetings не найдена в AI-Context")
            
            # Формируем свойства для создания страницы
            properties = {
                "Title": {
                    "title": [{"text": {"content": title[:100]}}]  # Ограничение Notion
                },
                "Date": {
                    "date": {"start": datetime.now().isoformat()}
                },
                "Status": {
                    "select": {"name": "Approved"}
                },
                "Summary": {
                    "rich_text": [{"text": {"content": summary[:2000]}}]  # Ограничение Notion
                },
                "Meeting ID": {
                    "rich_text": [{"text": {"content": meeting_id}}]
                }
            }
            
            # Добавляем участников как multi_select
            if participants:
                participant_options = []
                for participant in participants:
                    name = participant.get("name", "")
                    if name:
                        participant_options.append({"name": name[:100]})  # Ограничение Notion
                
                if participant_options:
                    properties["Participants"] = {
                        "multi_select": participant_options
                    }
            
            # Добавляем проекты как multi_select
            if projects:
                project_options = []
                for project in projects:
                    key = project.get("key", "")
                    name = project.get("name", key)
                    if key:
                        project_options.append({"name": f"{name} ({key})"[:100]})
                
                if project_options:
                    properties["Projects"] = {
                        "multi_select": project_options
                    }
            
            # Добавляем ключевые решения
            if key_decisions:
                decisions_text = "\n".join([
                    f"• {decision.get('title', '')}: {decision.get('description', '')}"
                    for decision in key_decisions[:10]  # Ограничиваем количество
                ])[:2000]  # Ограничение Notion
                
                properties["Key Decisions"] = {
                    "rich_text": [{"text": {"content": decisions_text}}]
                }
            
            # Добавляем задачи
            if action_items:
                tasks_text = "\n".join([
                    f"• {item.get('text', '')} - {item.get('assignee', 'Не назначен')} [{item.get('priority', 'Medium')}]"
                    for item in action_items[:20]  # Ограничиваем количество
                ])[:2000]  # Ограничение Notion
                
                properties["Action Items"] = {
                    "rich_text": [{"text": {"content": tasks_text}}]
                }
            
            # Добавляем инсайты
            if insights:
                insights_text = "\n".join([f"• {insight}" for insight in insights[:10]])[:2000]
                properties["Insights"] = {
                    "rich_text": [{"text": {"content": insights_text}}]
                }
            
            # Добавляем следующие шаги
            if next_steps:
                steps_text = "\n".join([f"• {step}" for step in next_steps[:10]])[:2000]
                properties["Next Steps"] = {
                    "rich_text": [{"text": {"content": steps_text}}]
                }
            
            # Создаем страницу в базе данных
            created_page = await self.client.pages.create(
                parent={"database_id": meetings_db_id},
                properties=properties
            )
            
            logger.info(f"✅ Встреча '{title}' добавлена в Notion Meetings database")
            return created_page
            
        except Exception as e:
            logger.error(f"❌ Ошибка при создании встречи в Notion: {e}")
            raise
    
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
                    elif prop_type == "select":
                        # Для tov_style и is_active (если они select)
                        select_option = prop_val.get("select")
                        if select_option:
                            value = select_option.get("name", "")
                            if "tov" in prop_name.lower() or "tone" in prop_name.lower() or "стиль" in prop_name.lower():
                                contact["tov_style"] = value.lower() if value else "default"
                            elif "active" in prop_name.lower() or "активен" in prop_name.lower() or "отчет" in prop_name.lower():
                                contact["is_active"] = value.lower() if value else "true"
                    elif prop_type == "checkbox":
                        # Для is_active (если это checkbox)
                        if "active" in prop_name.lower() or "активен" in prop_name.lower() or "отчет" in prop_name.lower() or "daily" in prop_name.lower():
                            contact["is_active"] = "true" if prop_val.get("checkbox", False) else "false"
                
                # Устанавливаем значения по умолчанию
                if "tov_style" not in contact:
                    contact["tov_style"] = "default"
                if "is_active" not in contact:
                    contact["is_active"] = "true"
                
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
    
    async def save_meeting_to_ai_context(
        self,
        ai_context_page_id: str,
        meeting_title: str,
        meeting_date: str,
        summary: str,
        full_transcript: str,
        duration: str,
        participants: Optional[List[str]] = None
    ) -> None:
        """
        Сохраняет встречу в страницу AI Context с полной структурой.
        
        Args:
            ai_context_page_id: ID страницы "AI Context"
            meeting_title: Название встречи
            meeting_date: Дата и время встречи
            summary: Саммари встречи
            full_transcript: Полная транскрипция
            duration: Длительность встречи
            participants: Список участников (опционально)
        """
        try:
            # Формируем структурированный контент
            content_blocks = []
            
            # Заголовок встречи
            content_blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": f"📅 {meeting_title}"
                            }
                        }
                    ]
                }
            })
            
            # Метаданные
            metadata_text = f"**Дата:** {meeting_date}\n**Длительность:** {duration}\n"
            if participants:
                metadata_text += f"**Участники:** {', '.join(participants)}\n"
            
            content_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": metadata_text.strip()
                            }
                        }
                    ]
                }
            })
            
            # Разделитель
            content_blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })
            
            # Саммари
            content_blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": "📋 Саммари"
                            }
                        }
                    ]
                }
            })
            
            content_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": summary
                            }
                        }
                    ]
                }
            })
            
            # Полная транскрипция
            content_blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": "📝 Полная транскрипция"
                            }
                        }
                    ]
                }
            })
            
            # Разбиваем транскрипцию на блоки с учетом лимита Notion API (2000 символов на блок)
            MAX_BLOCK_LENGTH = 2000
            transcript_paragraphs = full_transcript.split("\n\n")
            
            # Собираем параграфы в блоки, не превышающие лимит
            current_block_text = ""
            transcript_blocks = []
            
            for para in transcript_paragraphs:
                para = para.strip()
                if not para:
                    continue
                
                # Если добавление параграфа превысит лимит, сохраняем текущий блок
                if current_block_text and len(current_block_text) + len(para) + 2 > MAX_BLOCK_LENGTH:
                    transcript_blocks.append(current_block_text)
                    current_block_text = para
                else:
                    if current_block_text:
                        current_block_text += "\n\n" + para
                    else:
                        current_block_text = para
            
            # Добавляем последний блок
            if current_block_text:
                transcript_blocks.append(current_block_text)
            
            # Добавляем первые несколько блоков напрямую (для быстрого просмотра)
            visible_blocks = transcript_blocks[:3]
            for block_text in visible_blocks:
                # Разбиваем длинные блоки на части по 2000 символов
                for i in range(0, len(block_text), MAX_BLOCK_LENGTH):
                    chunk = block_text[i:i + MAX_BLOCK_LENGTH]
                    content_blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": chunk
                                    }
                                }
                            ]
                        }
                    })
            
            # Если есть еще блоки, добавляем их в toggle
            if len(transcript_blocks) > 3:
                remaining_blocks = transcript_blocks[3:]
                toggle_children = []
                
                for block_text in remaining_blocks:
                    # Разбиваем каждый блок на части по 2000 символов
                    for i in range(0, len(block_text), MAX_BLOCK_LENGTH):
                        chunk = block_text[i:i + MAX_BLOCK_LENGTH]
                        toggle_children.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": chunk
                                        }
                                    }
                                ]
                            }
                        })
                
                content_blocks.append({
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": f"Показать остальную транскрипцию ({len(remaining_blocks)} блоков)..."
                                }
                            }
                        ],
                        "children": toggle_children
                    }
                })
            
            # Разделитель в конце
            content_blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })
            
            # Добавляем все блоки на страницу
            await self.client.blocks.children.append(
                block_id=ai_context_page_id,
                children=content_blocks
            )
            
            logger.info(f"✅ Встреча сохранена в AI Context: {meeting_title}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении встречи в AI Context: {e}")
            raise
    
    async def append_to_meeting(self, page_id: str, text: str) -> None:
        """
        Добавляет текст к странице встречи (дозапись, не перезапись).
        Используется для потоковой транскрипции.
        
        Args:
            page_id: ID страницы Notion
            text: Текст для добавления
        """
        try:
            # Разбиваем текст на абзацы (по переносам строк)
            paragraphs = text.split('\n\n')
            
            blocks = []
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                
                # Если строка начинается с заголовка (## или ###), создаем heading
                if para.startswith('##'):
                    # Убираем ## и создаем heading_2
                    heading_text = para.lstrip('#').strip()
                    blocks.append({
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {"content": heading_text}
                                }
                            ]
                        }
                    })
                elif para.startswith('###'):
                    # Убираем ### и создаем heading_3
                    heading_text = para.lstrip('#').strip()
                    blocks.append({
                        "object": "block",
                        "type": "heading_3",
                        "heading_3": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {"content": heading_text}
                                }
                            ]
                        }
                    })
                else:
                    # Обычный параграф
                    # Обрабатываем HTML теги (если есть)
                    # Notion API не поддерживает HTML напрямую, поэтому просто убираем теги
                    import re
                    clean_text = re.sub(r'<[^>]+>', '', para)
                    
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {"content": clean_text}
                                }
                            ]
                        }
                    })
            
            if blocks:
                await self.client.blocks.children.append(
                    block_id=page_id,
                    children=blocks
                )
                logger.debug(f"Добавлено {len(blocks)} блоков на страницу {page_id}")
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении текста в Notion: {e}")
            raise
    
    async def get_or_create_meetings_page(self, parent_page_id: Optional[str] = None) -> str:
        """
        Получает или создает страницу "Встречи" на том же уровне, где находятся "Люди" и "Глоссарий".
        Внутри этой страницы будут создаваться подстраницы для каждой встречи.
        
        Args:
            parent_page_id: ID родительской страницы (если None, используется meeting_page_id)
            
        Returns:
            ID страницы "Встречи"
        """
        try:
            parent_id = parent_page_id or self.meeting_page_id
            if not parent_id:
                raise ValueError("Не указан parent_page_id и NOTION_MEETING_PAGE_ID не установлен")
            
            meetings_title = "Встречи"
            
            # Получаем дочерние страницы родительской страницы
            blocks = await self.client.blocks.children.list(parent_id)
            
            # Ищем существующую страницу "Встречи"
            for block in blocks.get("results", []):
                if block.get("type") == "child_page":
                    page_id = block["id"]
                    page_title = block.get("child_page", {}).get("title", "")
                    
                    if page_title == meetings_title or page_title.lower() == "встречи":
                        logger.info(f"✅ Найдена существующая страница 'Встречи': {page_id}")
                        return page_id
            
            # Если не найдена, создаем новую
            logger.info(f"📄 Создаю страницу 'Встречи' на уровне с 'Люди' и 'Глоссарий'...")
            
            # Получаем информацию о родительской странице
            parent_page = await self.client.pages.retrieve(parent_id)
            
            # Создаем новую страницу "Встречи"
            new_page = await self.client.pages.create(
                parent={"type": "page_id", "page_id": parent_id},
                properties={
                    "title": {
                        "title": [
                            {
                                "text": {
                                    "content": meetings_title
                                }
                            }
                        ]
                    }
                },
            )
            
            page_id = new_page["id"]
            logger.info(f"✅ Страница 'Встречи' создана: {page_id}")
            return page_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении/создании страницы 'Встречи': {e}")
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
        Страница создается внутри страницы "Встречи" (на том же уровне, где "Люди" и "Глоссарий").
        
        Args:
            meeting_title: Название встречи
            summary: Саммари встречи
            participants: Список участников
            action_items: Список action items
            parent_page_id: ID родительской страницы верхнего уровня (если None, используется meeting_page_id)
            
        Returns:
            ID созданной страницы встречи
        """
        try:
            # Получаем или создаем страницу "Встречи" на верхнем уровне
            # parent_page_id здесь - это страница верхнего уровня (где находятся "Люди" и "Глоссарий")
            top_level_parent = parent_page_id or self.meeting_page_id
            if not top_level_parent:
                raise ValueError("Не указан parent_page_id и NOTION_MEETING_PAGE_ID не установлен")
            
            # Получаем или создаем страницу "Встречи" внутри верхнего уровня
            meetings_page_id = await self.get_or_create_meetings_page(top_level_parent)
            
            # Теперь создаем страницу встречи внутри страницы "Встречи"
            parent_id = meetings_page_id
            
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
    
    async def get_or_create_ai_context_page(self, parent_page_id: Optional[str] = None) -> str:
        """
        Получает или создает страницу "AI Context" для хранения всех встреч и базы знаний.
        
        Args:
            parent_page_id: ID родительской страницы (если None, используется meeting_page_id)
            
        Returns:
            ID страницы "AI Context"
        """
        try:
            parent_id = parent_page_id or self.meeting_page_id
            if not parent_id:
                raise ValueError("Не указан parent_page_id и NOTION_MEETING_PAGE_ID не установлен")
            
            ai_context_title = "AI Context"
            
            # Получаем дочерние страницы
            blocks = await self.client.blocks.children.list(parent_id)
            
            # Ищем существующую страницу "AI Context"
            for block in blocks.get("results", []):
                if block.get("type") == "child_page":
                    page_id = block["id"]
                    page_title = block.get("child_page", {}).get("title", "")
                    
                    if page_title == ai_context_title:
                        logger.info(f"✅ Найдена существующая страница 'AI Context': {page_id}")
                        return page_id
            
            # Если не найдена, создаем новую
            logger.info(f"📄 Создаю страницу 'AI Context'...")
            
            # Получаем информацию о родительской странице для определения workspace
            parent_page = await self.client.pages.retrieve(parent_id)
            
            # Создаем новую страницу
            new_page = await self.client.pages.create(
                parent={"type": "page_id", "page_id": parent_id},
                properties={
                    "title": {
                        "title": [
                            {
                                "text": {
                                    "content": ai_context_title
                                }
                            }
                        ]
                    }
                },
                children=[
                    {
                        "object": "block",
                        "type": "heading_1",
                        "heading_1": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": "База знаний встреч"
                                    }
                                }
                            ]
                        }
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": "Эта страница содержит все транскрипции встреч, саммари и формирует базу знаний для AI."
                                    }
                                }
                            ]
                        }
                    }
                ]
            )
            
            page_id = new_page["id"]
            logger.info(f"✅ Создана страница 'AI Context': {page_id}")
            return page_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении/создании страницы 'AI Context': {e}")
            raise
    
    async def get_or_create_meeting_minutes_page(
        self, 
        parent_page_id: Optional[str] = None
    ) -> str:
        """
        Получает или создает страницу "Минутки встреч" для хранения структурированных минуток.
        
        Args:
            parent_page_id: ID родительской страницы (если None, используется meeting_page_id)
            
        Returns:
            ID страницы "Минутки встреч"
        """
        try:
            # Проверяем, указана ли страница минуток в настройках
            settings = get_settings()
            if settings.notion_meeting_minutes_page_id:
                # Проверяем, что страница существует
                try:
                    await self.client.pages.retrieve(settings.notion_meeting_minutes_page_id)
                    logger.info(f"✅ Используется страница 'Минутки встреч' из настроек: {settings.notion_meeting_minutes_page_id}")
                    return settings.notion_meeting_minutes_page_id
                except Exception as e:
                    logger.warning(f"⚠️ Страница минуток из настроек не найдена, создаем новую: {e}")
            
            parent_id = parent_page_id or self.meeting_page_id
            if not parent_id:
                raise ValueError("Не указан parent_page_id и NOTION_MEETING_PAGE_ID не установлен")
            
            minutes_title = "📋 Минутки встреч"
            
            # Получаем дочерние страницы
            blocks = await self.client.blocks.children.list(parent_id)
            
            # Ищем существующую страницу "Минутки встреч"
            for block in blocks.get("results", []):
                if block.get("type") == "child_page":
                    page_id = block["id"]
                    page_title = block.get("child_page", {}).get("title", "")
                    
                    if page_title == minutes_title or page_title == "Минутки встреч":
                        logger.info(f"✅ Найдена существующая страница 'Минутки встреч': {page_id}")
                        return page_id
            
            # Если не найдена, создаем новую
            logger.info(f"📄 Создаю страницу 'Минутки встреч'...")
            
            # Получаем информацию о родительской странице
            parent_page = await self.client.pages.retrieve(parent_id)
            
            # Создаем новую страницу
            new_page = await self.client.pages.create(
                parent={"type": "page_id", "page_id": parent_id},
                properties={
                    "title": {
                        "title": [
                            {
                                "text": {
                                    "content": minutes_title
                                }
                            }
                        ]
                    }
                },
                children=[
                    {
                        "object": "block",
                        "type": "heading_1",
                        "heading_1": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": "Минутки встреч"
                                    }
                                }
                            ]
                        }
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": "Эта страница содержит структурированные минутки всех встреч с тегами для организации."
                                    }
                                }
                            ]
                        }
                    }
                ]
            )
            
            page_id = new_page["id"]
            logger.info(f"✅ Создана страница 'Минутки встреч': {page_id}")
            return page_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении/создании страницы 'Минутки встреч': {e}")
            raise
    
    async def save_meeting_minutes(
        self,
        summary: str,
        action_items: Optional[List[Dict[str, Any]]] = None,
        participants: Optional[List[Dict[str, Any]]] = None,
        tags: Optional[List[str]] = None,
        meeting_date: Optional[str] = None,
        ai_context_link: Optional[str] = None,
        key_decisions: Optional[List[Dict[str, Any]]] = None,
        insights: Optional[List[str]] = None,
        next_steps: Optional[List[str]] = None,
        parent_page_id: Optional[str] = None
    ) -> str:
        """
        Сохраняет структурированную минутку встречи в страницу "Минутки встреч".
        
        Args:
            summary: Саммари встречи
            action_items: Список задач (опционально)
            participants: Список участников (опционально)
            tags: Список тегов для организации (опционально)
            meeting_date: Дата и время встречи (опционально)
            ai_context_link: Ссылка на полную транскрипцию в AI Context (опционально)
            parent_page_id: ID родительской страницы (если None, используется meeting_page_id)
            
        Returns:
            ID созданного блока минутки
        """
        try:
            # Получаем или создаем страницу минуток
            minutes_page_id = await self.get_or_create_meeting_minutes_page(parent_page_id)
            
            # Формируем структурированный контент
            content_blocks = []
            
            # Заголовок минутки
            meeting_title = f"📋 Минутки встречи"
            if meeting_date:
                meeting_title += f" - {meeting_date}"
            
            content_blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": meeting_title
                            }
                        }
                    ]
                }
            })
            
            # Метаданные
            metadata_parts = []
            if meeting_date:
                metadata_parts.append(f"**Дата:** {meeting_date}")
            if participants:
                participants_list = []
                for p in participants:
                    if isinstance(p, dict):
                        name = p.get('name', '')
                        username = p.get('telegram_username', '')
                        if username:
                            participants_list.append(f"@{username}")
                        elif name:
                            participants_list.append(name)
                    else:
                        participants_list.append(str(p))
                if participants_list:
                    metadata_parts.append(f"**Участники:** {', '.join(participants_list)}")
            if tags:
                tags_text = ' '.join([f"#{tag}" for tag in tags])
                metadata_parts.append(f"**Теги:** {tags_text}")
            
            if metadata_parts:
                content_blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "\n".join(metadata_parts)
                                }
                            }
                        ]
                    }
                })
            
            # Разделитель
            content_blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })
            
            # Суть (саммари)
            if summary:
                content_blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "Суть:"
                                }
                            }
                        ]
                    }
                })
                
                # Разбиваем саммари на параграфы, если есть переносы строк
                summary_lines = summary.split('\n')
                for line in summary_lines:
                    if line.strip():
                        content_blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": line.strip()
                                        }
                                    }
                                ]
                            }
                        })
            
            # Ключевые решения
            if key_decisions:
                content_blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "Ключевые решения:"
                                }
                            }
                        ]
                    }
                })
                
                for decision in key_decisions:
                    if isinstance(decision, dict):
                        title = decision.get('title', '')
                        description = decision.get('description', '')
                        impact = decision.get('impact', '')
                        
                        decision_text = f"**{title}**\n{description}"
                        if impact:
                            decision_text += f"\n*Влияние: {impact}*"
                        
                        content_blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": decision_text
                                        },
                                        "annotations": {
                                            "bold": True
                                        }
                                    }
                                ]
                            }
                        })
            
            # Инсайты
            if insights:
                content_blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "Инсайты:"
                                }
                            }
                        ]
                    }
                })
                
                for insight in insights:
                    if insight.strip():
                        content_blocks.append({
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": insight.strip()
                                        }
                                    }
                                ]
                            }
                        })
            
            # Следующие шаги
            if next_steps:
                content_blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "Следующие шаги:"
                                }
                            }
                        ]
                    }
                })
                
                for step in next_steps:
                    if step.strip():
                        content_blocks.append({
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": step.strip()
                                        }
                                    }
                                ]
                            }
                        })
            
            # Задачи
            if action_items:
                content_blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "Задачи:"
                                }
                            }
                        ]
                    }
                })
                
                for item in action_items:
                    if isinstance(item, dict):
                        priority_emoji = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}.get(
                            item.get('priority', 'Medium'), '⚪'
                        )
                        text = item.get('text', '') or item.get('title', '')
                        assignee = item.get('assignee', '')
                        
                        item_text = f"{priority_emoji} {text}"
                        if assignee:
                            item_text += f" → {assignee}"
                        
                        content_blocks.append({
                            "object": "block",
                            "type": "to_do",
                            "to_do": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": item_text
                                        }
                                    }
                                ],
                                "checked": False
                            }
                        })
                    else:
                        content_blocks.append({
                            "object": "block",
                            "type": "to_do",
                            "to_do": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": str(item)
                                        }
                                    }
                                ],
                                "checked": False
                            }
                        })
            
            # Ссылка на полную транскрипцию
            if ai_context_link:
                # ai_context_link может быть page_id (UUID) или URL
                page_id_from_link = None
                import re
                
                # Если это UUID (с дефисами или без)
                if re.match(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$', ai_context_link):
                    page_id_from_link = ai_context_link
                elif re.match(r'^[0-9a-fA-F]{32}$', ai_context_link):
                    # Преобразуем в формат с дефисами
                    hex_id = ai_context_link
                    page_id_from_link = f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
                elif ai_context_link.startswith("http"):
                    # Извлекаем ID из URL
                    match = re.search(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', ai_context_link)
                    if match:
                        page_id_from_link = match.group(0)
                    else:
                        # Пробуем без дефисов
                        match = re.search(r'[0-9a-fA-F]{32}', ai_context_link)
                        if match:
                            # Преобразуем в формат с дефисами
                            hex_id = match.group(0)
                            page_id_from_link = f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
                
                # Если удалось извлечь page_id, используем mention
                if page_id_from_link:
                    try:
                        content_blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": "Ссылка на полную транскрипцию: "
                                        },
                                        "annotations": {
                                            "bold": True
                                        }
                                    },
                                    {
                                        "type": "mention",
                                        "mention": {
                                            "type": "page",
                                            "page": {
                                                "id": page_id_from_link
                                            }
                                        }
                                    }
                                ]
                            }
                        })
                    except Exception as e:
                        logger.warning(f"Не удалось создать mention ссылку, используем текстовую: {e}")
                        # Fallback на текстовую ссылку
                        content_blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": f"Ссылка на полную транскрипцию: {ai_context_link}",
                                            "link": {
                                                "url": ai_context_link if ai_context_link.startswith("http") else f"https://www.notion.so/{ai_context_link.replace('-', '')}"
                                            }
                                        },
                                        "annotations": {
                                            "bold": True
                                        }
                                    }
                                ]
                            }
                        })
                else:
                    # Используем текстовую ссылку с URL
                    content_blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": "Ссылка на полную транскрипцию: ",
                                        "link": None
                                    },
                                    "annotations": {
                                        "bold": True
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": {
                                        "content": ai_context_link.replace("**", "").replace("[", "").replace("]", ""),
                                        "link": {
                                            "url": ai_context_link if ai_context_link.startswith("http") else f"https://www.notion.so/{ai_context_link.replace('-', '')}"
                                        }
                                    }
                                }
                            ]
                        }
                    })
            
            # Добавляем разделитель между минуток
            content_blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })
            
            # Добавляем блоки на страницу минуток
            logger.info(f"💾 Добавляю {len(content_blocks)} блоков на страницу минуток...")
            response = await self.client.blocks.children.append(
                block_id=minutes_page_id,
                children=content_blocks
            )
            
            # Извлекаем ID первого созданного блока (если есть)
            created_block_id = None
            if response and response.get("results") and len(response["results"]) > 0:
                created_block_id = response["results"][0].get("id")
            
            logger.info(f"✅ Минутка встречи сохранена в страницу 'Минутки встреч' (page_id: {minutes_page_id}, первый блок: {created_block_id})")
            return minutes_page_id
            
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении минутки встречи: {e}")
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

    async def get_last_created_page(self, parent_page_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Получает последнюю созданную дочернюю страницу (встречу).
        
        Args:
            parent_page_id: ID родительской страницы (если None, используется meeting_page_id)
            
        Returns:
            Словарь с данными страницы (id, title, content) или None
        """
        try:
            parent_id = parent_page_id or self.meeting_page_id
            if not parent_id:
                logger.warning("Не указан ID родительской страницы для поиска последней встречи")
                return None
            
            # Получаем блоки (дочерние элементы)
            blocks = await self.client.blocks.children.list(parent_id)
            results = blocks.get("results", [])
            
            # Ищем child_page с конца (так как новые добавляются в конец)
            for block in reversed(results):
                if block.get("type") == "child_page":
                    page_id = block["id"]
                    title = block.get("child_page", {}).get("title", "")
                    
                    # Игнорируем служебные страницы
                    if title in ["AI Context", "Минутки встреч", "База знаний"]:
                        continue
                    
                    logger.info(f"Найден кандидат на последнюю встречу: {title} ({page_id})")
                    
                    # Получаем контент страницы
                    content = await self.get_page_content(page_id, include_metadata=True)
                    
                    return {
                        "id": page_id,
                        "title": title,
                        "content": content
                    }
            
            logger.info("Не найдено ни одной подходящей страницы встречи")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при поиске последней страницы встречи: {e}")
            return None
