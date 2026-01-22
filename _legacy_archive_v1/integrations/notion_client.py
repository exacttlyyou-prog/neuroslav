"""
Асинхронный клиент для работы с Notion API.
"""
from notion_client import AsyncClient
from loguru import logger
from typing import Dict, Any

from core.config import get_settings
from core.schemas import ActionItem


class NotionTaskCreator:
    """Создатель задач в Notion."""
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncClient(auth=settings.notion_token)
    
    async def get_page_content(self, page_id: str) -> str:
        """
        Получает контент страницы Notion.
        
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
    
    async def create_tasks(
        self,
        page_id: str,
        action_items: list[ActionItem],
        database_id: str | None = None
    ) -> list[str]:
        """
        Создает задачи (To-Do блоки) в Notion.
        
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
                    page_properties = {
                        "Name": {
                            "title": [{"text": {"content": item.text}}]
                        }
                    }
                    
                    if item.priority:
                        page_properties["Priority"] = {
                            "select": {"name": item.priority}
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
                        page_id=page_id,
                        children=[block_data]
                    )
                    created_task_ids.append(new_block["results"][0]["id"])
            
            logger.info(f"Создано {len(created_task_ids)} задач в Notion")
            return created_task_ids
            
        except Exception as e:
            logger.error(f"Ошибка при создании задач в Notion: {e}")
            raise
    
    async def update_page_properties(
        self,
        page_id: str,
        properties: Dict[str, Any]
    ) -> None:
        """
        Обновляет свойства страницы Notion.
        
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

