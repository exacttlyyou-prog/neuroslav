"""
Роутер агентов для автоматической классификации и маршрутизации сообщений.
"""
from typing import Dict, Any
from loguru import logger

from app.services.ollama_service import OllamaService
from app.services.context_loader import ContextLoader
from app.models.schemas import IntentClassification, AgentResponse


class AgentRouter:
    """Роутер для классификации и маршрутизации сообщений к агентам."""
    
    def __init__(self):
        self.ollama = OllamaService()
        self.context_loader = ContextLoader()
    
    async def classify(self, user_input: str) -> IntentClassification:
        """
        Классифицирует сообщение пользователя и определяет нужного агента.
        
        Args:
            user_input: Сообщение пользователя
            
        Returns:
            IntentClassification с типом агента и извлеченными данными
        """
        try:
            prompt = f"""Классифицируй сообщение пользователя и определи, какой агент должен его обработать.

Типы агентов:
- task: задача с deadline, напоминание, todo, "нужно сделать", "не забудь"
- meeting: репорт встречи, саммари встречи, "обработай встречу", "сделай репорт"
- message: отложенное сообщение для отправки, "напомни отправить", "сообщение для X"
- knowledge: сохранить информацию в базу знаний, "запомни", "сохрани это"
- rag_query: вопрос, поиск информации, "найди", "когда было", "что такое"
- default: общий ответ, помощь, неопределенное намерение

Сообщение пользователя: "{user_input}"

Верни классификацию в формате JSON с полями:
- agent_type: один из типов выше
- confidence: уверенность (0.0-1.0)
- extracted_data: объект с извлеченными данными (deadline, участники, проекты, etc.)
- reasoning: краткое объяснение почему выбран этот тип

Примеры:
- "Нужно сделать презентацию к пятнице" → task (deadline: пятница)
- "Обработай последнюю встречу" → meeting
- "Напомни отправить отчет Ивану завтра" → message (получатель: Иван, время: завтра)
- "Запомни что проект Альфа запускается в марте" → knowledge
- "Когда была последняя встреча по проекту Бета?" → rag_query
- "Привет, как дела?" → default
"""
            
            classification = await self.ollama.generate_structured(
                prompt=prompt,
                response_schema=IntentClassification,
                temperature=0.3  # Низкая температура для более детерминированной классификации
            )
            
            logger.info(f"Классифицировано как {classification.agent_type} (confidence: {classification.confidence:.2f})")
            return classification
            
        except Exception as e:
            logger.error(f"Ошибка при классификации: {e}")
            # Fallback: возвращаем default агент
            return IntentClassification(
                agent_type="default",
                confidence=0.5,
                extracted_data={},
                reasoning=f"Ошибка классификации: {str(e)}"
            )
    
    async def route(self, user_input: str, classification: IntentClassification) -> AgentResponse:
        """
        Маршрутизирует сообщение к нужному агенту.
        
        Args:
            user_input: Сообщение пользователя
            classification: Результат классификации
            
        Returns:
            AgentResponse от агента
        """
        agent_type = classification.agent_type
        
        try:
            if agent_type == "task":
                from app.services.agents.task_agent import TaskAgent
                agent = TaskAgent()
            elif agent_type == "meeting":
                from app.services.agents.meeting_agent import MeetingAgent
                agent = MeetingAgent()
            elif agent_type == "message":
                from app.services.agents.message_agent import MessageAgent
                agent = MessageAgent()
            elif agent_type == "knowledge":
                from app.services.agents.knowledge_agent import KnowledgeAgent
                agent = KnowledgeAgent()
            elif agent_type == "rag_query":
                from app.services.agents.rag_agent import RAGAgent
                agent = RAGAgent()
            else:
                from app.services.agents.default_agent import DefaultAgent
                agent = DefaultAgent()
            
            # Обрабатываем через агента
            response = await agent.process(user_input, classification)
            return response
            
        except ImportError as e:
            logger.error(f"Агент {agent_type} не найден: {e}")
            # Fallback к default агенту
            from app.services.agents.default_agent import DefaultAgent
            agent = DefaultAgent()
            return await agent.process(user_input, classification)
        except Exception as e:
            logger.error(f"Ошибка при обработке агентом {agent_type}: {e}")
            raise
