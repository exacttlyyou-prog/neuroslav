"""
Базовый класс для всех агентов.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from loguru import logger
import re

from app.services.rag_service import RAGService
from app.services.context_loader import ContextLoader
from app.services.ollama_service import OllamaService
from app.models.schemas import IntentClassification, AgentResponse


class BaseAgent(ABC):
    """Базовый класс для всех агентов."""
    
    def __init__(self):
        self.rag = RAGService()
        self.context_loader = ContextLoader()
        self.ollama = OllamaService(context_loader=self.context_loader)
        
        # Флаг для отслеживания инициализации контекста
        self._context_initialized = False
    
    async def process(self, user_input: str, classification: IntentClassification, sender_username: str = None) -> AgentResponse:
        """
        Главный метод обработки сообщения.
        
        Args:
            user_input: Сообщение пользователя
            classification: Результат классификации
            sender_username: Telegram username отправителя (опционально)
            
        Returns:
            AgentResponse с результатом обработки
        """
        try:
            # Шаг 0: Убеждаемся что контекст синхронизирован с Notion
            if not self._context_initialized:
                await self.context_loader.ensure_notion_sync()
                self._context_initialized = True
            
            # Шаг 1: Получить контекст из RAG
            logger.info(f"Получение контекста из RAG для {self.__class__.__name__}...")
            context = await self._get_rag_context(user_input)
            
            # Шаг 2: Обработать через конкретный агент с передачей username
            logger.info(f"Обработка через {self.__class__.__name__}...")
            result = await self._process_with_context(user_input, classification, context, sender_username=sender_username)
            
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
        context: List[str],
        sender_username: str = None
    ) -> Dict[str, Any]:
        """
        Обрабатывает сообщение с контекстом из RAG.
        Должен быть реализован в дочерних классах.
        
        Args:
            user_input: Сообщение пользователя
            classification: Результат классификации
            context: Контекст из RAG
            sender_username: Telegram username отправителя (опционально)
        
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
    
    def get_next_agents(self, result: Dict[str, Any]) -> List[str]:
        """
        Определяет, какие агенты должны работать после текущего.
        
        Args:
            result: Результат обработки текущего агента
            
        Returns:
            Список типов агентов для следующего шага
        """
        # По умолчанию нет следующих агентов
        # Переопределяется в дочерних классах
        return []
    
    def can_chain_with(self, other_agent_type: str) -> bool:
        """
        Проверяет возможность цепочки с другим агентом.
        
        Args:
            other_agent_type: Тип другого агента
            
        Returns:
            True если возможна цепочка
        """
        # По умолчанию цепочки не поддерживаются
        # Переопределяется в дочерних классах
        return False
    
    def clean_response(self, response: str) -> str:
        """
        Единый cleaning pipeline для всех ответов агентов.
        Убирает технические символы и форматирует ответ в пользовательском стиле.
        
        Args:
            response: Сырой ответ от LLM или агента
            
        Returns:
            Очищенный ответ в пользовательском формате
        """
        if not response or not isinstance(response, str):
            return ""
        
        # Убираем технические префиксы и заголовки
        tech_patterns = [
            # Паттерны агентов
            r"🤖\s*<b>.*?Agent.*?</b>:?",
            r"🤖\s*.*?Agent:?",
            r"\b\w+Agent:?\s*",
            
            # Технические сообщения
            r"🤖\s*Обрабатываю\.\.\.?",
            r"🤖\s*<b>Обрабатываю\.\.\.?</b>",
            r"Обрабатываю\.\.\.?",
            
            # Markdown и HTML заголовки
            r"\*\*Summary:?\*\*",
            r"\*\*Context:?\*\*", 
            r"\*\*Details:?\*\*",
            r"\*\*Result:?\*\*",
            r"\*\*Information:?\*\*",
            r"\*\*Analysis:?\*\*",
            r"\*\*Response:?\*\*",
            r"<b>.*?(Summary|Context|Details|Result|Information|Analysis|Response).*?</b>:?",
            
            # Русские технические заголовки
            r"КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ:?",
            r"НАЙДЕННАЯ ИНФОРМАЦИЯ:?",
            r"РЕЗУЛЬТАТ ПОИСКА:?",
            r"АНАЛИЗ ВСТРЕЧИ:?",
            r"САММАРИ:?",
            r"КЛЮЧЕВЫЕ РЕШЕНИЯ:?",
            
            # Процессуальные сообщения
            r"🔍\s*Ищу информацию\.\.\.?",
            r"🔄\s*Загружаю контекст\.\.\.?",
            r"📊\s*Анализирую данные\.\.\.?",
            r"✅\s*Обработано\.?",
            r"✅\s*Сделано\.?",
            
            # Разделители и форматирование
            r"^[-=_]+$",  # Строки из дефисов/равно/подчеркиваний
            r"^#+\s*",   # Markdown заголовки
        ]
        
        # Применяем все паттерны
        cleaned = response
        for pattern in tech_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
        
        # Убираем Markdown форматирование (жирный, курсив, подчеркивание)
        # Заменяем на обычный текст, сохраняя содержимое
        cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)  # **текст** -> текст
        cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)    # *текст* -> текст
        cleaned = re.sub(r'__([^_]+)__', r'\1', cleaned)    # __текст__ -> текст
        cleaned = re.sub(r'_([^_]+)_', r'\1', cleaned)      # _текст_ -> текст
        cleaned = re.sub(r'~~([^~]+)~~', r'\1', cleaned)    # ~~текст~~ -> текст
        
        # Убираем HTML теги (если остались после предыдущей обработки)
        cleaned = re.sub(r'<[^>]+>', '', cleaned)  # Удаляем все HTML теги
        
        # Убираем специальные символы из LLM ответов
        cleaned = re.sub(r'```[\s\S]*?```', '', cleaned)  # Удаляем блоки кода
        cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)     # Удаляем инлайн код
        cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', cleaned)  # Удаляем markdown ссылки [текст](url) -> текст
        
        # Убираем лишние переносы строк и пробелы
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)  # Не более 2 переносов подряд
        cleaned = re.sub(r'^\s+|\s+$', '', cleaned)   # Пробелы в начале и конце
        
        # Убираем пустые строки в начале и конце каждой строки
        lines = [line.strip() for line in cleaned.split('\n')]
        cleaned = '\n'.join(line for line in lines if line)
        
        # Если результат пустой, возвращаем заглушку
        if not cleaned or len(cleaned.strip()) < 3:
            return "Готово."
        
        return cleaned
    
    def format_user_friendly_actions(self, actions: List[Dict[str, Any]]) -> List[str]:
        """
        Преобразует технические действия в пользовательский формат.
        
        Args:
            actions: Список технических действий агента
            
        Returns:
            Список пользовательских описаний действий
        """
        if not actions:
            return []
        
        user_friendly = []
        action_map = {
            "task_created": "📋 Задача создана",
            "meeting_processed": "🎯 Встреча обработана", 
            "knowledge_saved": "🧠 Информация сохранена",
            "message_scheduled": "📨 Сообщение запланировано",
            "search_completed": "🔍 Поиск завершен",
            "analysis_done": "📊 Анализ выполнен",
            "data_updated": "💾 Данные обновлены",
            "notification_sent": "📢 Уведомление отправлено",
        }
        
        # Список технических действий, которые не показываем пользователю
        hidden_actions = {"rag_search", "context_loaded", "validation_passed", "cache_hit"}
        
        for action in actions:
            action_type = action.get("type", "unknown")
            
            # Пропускаем скрытые технические действия
            if action_type in hidden_actions:
                continue
            
            # Используем маппинг или дефолтное описание
            if action_type in action_map:
                user_friendly.append(action_map[action_type])
            elif action_type != "unknown":
                # Преобразуем snake_case в человеческий вид
                readable = action_type.replace("_", " ").title()
                user_friendly.append(f"✅ {readable}")
        
        return user_friendly
