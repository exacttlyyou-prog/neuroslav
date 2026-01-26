"""
Unit тесты для BaseAgent.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.agents.base_agent import BaseAgent
from app.models.schemas import IntentClassification, AgentResponse


class TestAgent(BaseAgent):
    """Тестовая реализация BaseAgent для тестирования."""
    
    async def _process_with_context(self, user_input: str, classification: IntentClassification, context):
        return {
            "response": f"Тестовый ответ на: {user_input}",
            "actions": [{"type": "test_action", "details": "test"}],
            "metadata": {"test": True},
            "should_save_to_rag": True
        }
    
    def get_agent_type(self) -> str:
        return "test"


class TestBaseAgentResponseCleaning:
    """Тесты для очистки ответов BaseAgent."""
    
    @pytest.fixture
    def agent(self):
        return TestAgent()
    
    def test_clean_empty_response(self, agent):
        """Тест очистки пустого ответа."""
        assert agent.clean_response("") == ""
        assert agent.clean_response(None) == ""
        assert agent.clean_response("   ") == "Готово."
    
    def test_clean_technical_patterns(self, agent):
        """Тест удаления технических паттернов."""
        responses_to_clean = [
            "🤖 <b>taskAgent:</b> Создаю задачу",
            "🤖 testAgent: Выполняю действие", 
            "TestAgent: Результат работы",
            "🤖 Обрабатываю...",
            "**Summary:** Краткое содержание",
            "КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ: важная информация",
            "🔍 Ищу информацию... результат поиска",
            "✅ Обработано. Готово",
        ]
        
        expected_results = [
            "Создаю задачу",
            "Выполняю действие",
            "Результат работы", 
            "",
            "Краткое содержание",
            "важная информация",
            "результат поиска",
            "Готово",
        ]
        
        for response, expected in zip(responses_to_clean, expected_results):
            cleaned = agent.clean_response(response)
            if not expected:
                assert cleaned == "Готово."
            else:
                assert cleaned == expected
    
    def test_clean_multiple_newlines(self, agent):
        """Тест очистки множественных переносов строк."""
        response = "Строка 1\n\n\n\nСтрока 2\n\n\n\nСтрока 3"
        expected = "Строка 1\n\nСтрока 2\n\nСтрока 3"
        
        assert agent.clean_response(response) == expected
    
    def test_clean_markdown_headers(self, agent):
        """Тест удаления markdown заголовков."""
        response = "## Заголовок\nТекст содержания\n### Подзаголовок\nБольше текста"
        expected = "Заголовок\nТекст содержания\nПодзаголовок\nБольше текста"
        
        assert agent.clean_response(response) == expected
    
    def test_clean_preserves_content(self, agent):
        """Тест что полезный контент сохраняется."""
        response = "Задача успешно создана. Дедлайн: пятница. Ответственный: Иван."
        
        cleaned = agent.clean_response(response)
        
        assert "Задача успешно создана" in cleaned
        assert "Дедлайн: пятница" in cleaned
        assert "Ответственный: Иван" in cleaned


class TestBaseAgentActionFormatting:
    """Тесты для форматирования действий BaseAgent."""
    
    @pytest.fixture
    def agent(self):
        return TestAgent()
    
    def test_format_empty_actions(self, agent):
        """Тест форматирования пустого списка действий."""
        assert agent.format_user_friendly_actions([]) == []
        assert agent.format_user_friendly_actions(None) == []
    
    def test_format_known_actions(self, agent):
        """Тест форматирования известных действий."""
        actions = [
            {"type": "task_created", "details": "test"},
            {"type": "meeting_processed", "details": "test"},
            {"type": "knowledge_saved", "details": "test"},
            {"type": "message_scheduled", "details": "test"},
        ]
        
        result = agent.format_user_friendly_actions(actions)
        
        expected = [
            "📋 Задача создана",
            "🎯 Встреча обработана", 
            "🧠 Информация сохранена",
            "📨 Сообщение запланировано",
        ]
        
        assert result == expected
    
    def test_format_hidden_actions(self, agent):
        """Тест скрытия технических действий."""
        actions = [
            {"type": "rag_search", "details": "should be hidden"},
            {"type": "context_loaded", "details": "should be hidden"},
            {"type": "validation_passed", "details": "should be hidden"},
            {"type": "cache_hit", "details": "should be hidden"},
            {"type": "task_created", "details": "should be shown"},
        ]
        
        result = agent.format_user_friendly_actions(actions)
        
        assert result == ["📋 Задача создана"]
    
    def test_format_unknown_actions(self, agent):
        """Тест форматирования неизвестных действий."""
        actions = [
            {"type": "custom_action", "details": "test"},
            {"type": "another_custom_action", "details": "test"},
        ]
        
        result = agent.format_user_friendly_actions(actions)
        
        expected = [
            "✅ Custom Action",
            "✅ Another Custom Action",
        ]
        
        assert result == expected
    
    def test_format_mixed_actions(self, agent):
        """Тест форматирования смешанных действий."""
        actions = [
            {"type": "rag_search", "details": "hidden"},
            {"type": "task_created", "details": "shown"},
            {"type": "unknown", "details": "hidden"},
            {"type": "custom_action", "details": "shown"},
        ]
        
        result = agent.format_user_friendly_actions(actions)
        
        expected = [
            "📋 Задача создана",
            "✅ Custom Action",
        ]
        
        assert result == expected


@pytest.mark.asyncio
class TestBaseAgentProcessing:
    """Тесты для обработки BaseAgent."""
    
    @pytest.fixture
    def agent(self, mock_rag_service, mock_context_loader):
        """Создает агента с замоканными зависимостями."""
        agent = TestAgent()
        agent.rag = mock_rag_service
        agent.context_loader = mock_context_loader
        return agent
    
    async def test_successful_processing(self, agent):
        """Тест успешной обработки."""
        user_input = "создай задачу тестирования"
        classification = IntentClassification(
            agent_type="test",
            confidence=0.95,
            extracted_data={}
        )
        
        result = await agent.process(user_input, classification)
        
        assert isinstance(result, AgentResponse)
        assert result.agent_type == "test"
        assert result.success is True
        assert "Тестовый ответ на: создай задачу тестирования" in result.response
        assert len(result.actions) == 1
        assert result.actions[0]["type"] == "test_action"
    
    async def test_context_initialization(self, agent):
        """Тест инициализации контекста."""
        user_input = "тест"
        classification = IntentClassification(
            agent_type="test",
            confidence=0.95,
            extracted_data={}
        )
        
        await agent.process(user_input, classification)
        
        # Проверяем что контекст был инициализирован
        agent.context_loader.ensure_notion_sync.assert_called_once()
    
    async def test_rag_context_retrieval(self, agent):
        """Тест получения контекста из RAG."""
        user_input = "найди информацию о проекте"
        classification = IntentClassification(
            agent_type="test",
            confidence=0.95,
            extracted_data={}
        )
        
        # Настраиваем моки
        agent.rag.search_similar_meetings.return_value = [
            {"content": "контент встречи"}
        ]
        agent.rag.search_knowledge.return_value = [
            {"content": "контент знаний"}
        ]
        
        await agent.process(user_input, classification)
        
        # Проверяем что RAG был вызван
        agent.rag.search_similar_meetings.assert_called_once_with(user_input, limit=2)
        agent.rag.search_knowledge.assert_called_once_with(user_input, limit=2)
    
    async def test_error_handling(self, agent):
        """Тест обработки ошибок."""
        # Заставляем _process_with_context выбросить ошибку
        original_method = agent._process_with_context
        
        async def failing_method(*args, **kwargs):
            raise Exception("Тестовая ошибка")
        
        agent._process_with_context = failing_method
        
        user_input = "тест"
        classification = IntentClassification(
            agent_type="test",
            confidence=0.95,
            extracted_data={}
        )
        
        result = await agent.process(user_input, classification)
        
        assert isinstance(result, AgentResponse)
        assert result.success is False
        assert "Ошибка при обработке" in result.response
        assert "Тестовая ошибка" in result.response
        
        # Восстанавливаем оригинальный метод
        agent._process_with_context = original_method
    
    async def test_context_preservation(self, agent):
        """Тест сохранения контекста между вызовами."""
        user_input = "тест"
        classification = IntentClassification(
            agent_type="test",
            confidence=0.95,
            extracted_data={}
        )
        
        # Первый вызов
        await agent.process(user_input, classification)
        
        # Второй вызов - контекст не должен инициализироваться снова
        await agent.process(user_input, classification)
        
        # ensure_notion_sync должен быть вызван только один раз
        assert agent.context_loader.ensure_notion_sync.call_count == 1


class TestBaseAgentChaining:
    """Тесты для цепочек агентов."""
    
    @pytest.fixture
    def agent(self):
        return TestAgent()
    
    def test_get_next_agents_default(self, agent):
        """Тест получения следующих агентов (по умолчанию пусто)."""
        result = {"test": True}
        next_agents = agent.get_next_agents(result)
        
        assert next_agents == []
    
    def test_can_chain_with_default(self, agent):
        """Тест возможности цепочки (по умолчанию False)."""
        assert agent.can_chain_with("task") is False
        assert agent.can_chain_with("meeting") is False