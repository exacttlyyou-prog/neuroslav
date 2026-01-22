"""
Базовый класс для всех агентов.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from loguru import logger

from app.services.rag_service import RAGService
from app.services.context_loader import ContextLoader
from app.models.schemas import IntentClassification, AgentResponse


class BaseAgent(ABC):
    """Базовый класс для всех агентов."""
    
    def __init__(self):
        self.rag = RAGService()
        self.context_loader = ContextLoader()
    
    async def process(self, user_input: str, classification: IntentClassification) -> AgentResponse:
        """
        Главный метод обработки сообщения.
        
        Args:
            user_input: Сообщение пользователя
            classification: Результат классификации
            
        Returns:
            AgentResponse с результатом обработки
        """
        try:
            # Шаг 1: Получить контекст из RAG
            logger.info(f"Получение контекста из RAG для {self.__class__.__name__}...")
            context = await self._get_rag_context(user_input)
            
            # Шаг 2: Обработать через конкретный агент
            logger.info(f"Обработка через {self.__class__.__name__}...")
            result = await self._process_with_context(user_input, classification, context)
            
            # Шаг 3: Сохранить результат в RAG
            if result.get("should_save_to_rag", True):
                await self._save_to_rag(user_input, result)
            
            # Шаг 4: Вернуть ответ
            return AgentResponse(
                agent_type=self.get_agent_type(),
                response=result.get("response", ""),
                actions=result.get("actions", []),
                metadata=result.get("metadata", {})
            )
            
        except Exception as e:
            logger.error(f"Ошибка в {self.__class__.__name__}: {e}")
            return AgentResponse(
                agent_type=self.get_agent_type(),
                response=f"Ошибка при обработке: {str(e)}",
                actions=[],
                metadata={"error": str(e)}
            )
    
    async def _get_rag_context(self, user_input: str) -> List[str]:
        """
        Получает контекст из RAG для обогащения ответа.
        
        Args:
            user_input: Сообщение пользователя
            
        Returns:
            Список релевантных фрагментов из RAG
        """
        try:
            # Ищем похожий контент в разных коллекциях RAG
            context_items = []
            
            # Поиск в встречах
            similar_meetings = await self.rag.search_similar_meetings(user_input, limit=2)
            for meeting in similar_meetings:
                if isinstance(meeting, dict):
                    context_items.append(meeting.get("content", ""))
            
            # Поиск в знаниях
            similar_knowledge = await self.rag.search_knowledge(user_input, limit=2)
            for knowledge in similar_knowledge:
                if isinstance(knowledge, dict):
                    context_items.append(knowledge.get("content", ""))
            
            return context_items
            
        except Exception as e:
            logger.warning(f"Ошибка при получении контекста из RAG: {e}")
            return []
    
    async def _save_to_rag(self, user_input: str, result: Dict[str, Any]) -> None:
        """
        Сохраняет результат обработки в RAG.
        
        Args:
            user_input: Исходное сообщение
            result: Результат обработки
        """
        try:
            # Сохраняем в соответствующую коллекцию RAG
            # Переопределяется в дочерних классах
            pass
        except Exception as e:
            logger.warning(f"Ошибка при сохранении в RAG: {e}")
    
    @abstractmethod
    async def _process_with_context(
        self,
        user_input: str,
        classification: IntentClassification,
        context: List[str]
    ) -> Dict[str, Any]:
        """
        Обрабатывает сообщение с контекстом из RAG.
        Должен быть реализован в дочерних классах.
        
        Args:
            user_input: Сообщение пользователя
            classification: Результат классификации
            context: Контекст из RAG
            
        Returns:
            Словарь с результатом:
            {
                "response": str,
                "actions": List[Dict],
                "metadata": Dict,
                "should_save_to_rag": bool
            }
        """
        pass
    
    @abstractmethod
    def get_agent_type(self) -> str:
        """Возвращает тип агента."""
        pass
