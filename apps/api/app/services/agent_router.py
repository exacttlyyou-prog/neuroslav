"""
Роутер агентов для автоматической классификации и маршрутизации сообщений.
"""
from typing import Dict, Any, List
from datetime import datetime
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
    
    async def route(self, user_input: str, classification: IntentClassification, sender_username: str = None) -> AgentResponse:
        """
        Маршрутизирует сообщение к нужному агенту.
        
        Args:
            user_input: Сообщение пользователя
            classification: Результат классификации
            sender_username: Telegram username отправителя (опционально)
            
        Returns:
            AgentResponse от агента с трассировкой решений
        """
        agent_type = classification.agent_type
        start_time = datetime.now()
        
        # Инициализируем трассировку решений
        decision_trace = {
            "selected_agent": agent_type,
            "confidence": classification.confidence,
            "reasoning": classification.reasoning,
            "start_time": start_time.isoformat(),
            "end_time": None,
            "processing_time_ms": None,
            "agent_chain": [],
            "classification_details": {
                "extracted_data": classification.extracted_data
            }
        }
        
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
            
            # Обрабатываем через агента с передачей username
            response = await agent.process(user_input, classification, sender_username=sender_username)
            
            # Проверяем, нужны ли дополнительные агенты (цепочка)
            next_agents = agent.get_next_agents({
                "response": response.response,
                "actions": response.actions,
                "metadata": response.metadata
            })
            
            # Если есть следующие агенты, запускаем их
            if next_agents:
                logger.info(f"Запуск цепочки агентов после {agent_type}: {next_agents}")
                decision_trace["agent_chain"] = next_agents.copy()
                chain_responses = await self.coordinate_agents(response, user_input, next_agents)
                # Объединяем результаты цепочки в метаданные
                response.metadata["chain_responses"] = [
                    {
                        "agent_type": r.agent_type,
                        "response": r.response,
                        "actions": r.actions
                    }
                    for r in chain_responses
                ]
            
            # Завершаем трассировку
            end_time = datetime.now()
            decision_trace["end_time"] = end_time.isoformat()
            decision_trace["processing_time_ms"] = int((end_time - start_time).total_seconds() * 1000)
            
            # Добавляем трассировку в метаданные ответа
            if response.metadata is None:
                response.metadata = {}
            response.metadata["decision_trace"] = decision_trace
            
            logger.info(f"Обработка завершена за {decision_trace['processing_time_ms']}мс агентом {agent_type}")
            
            return response
            
        except ImportError as e:
            logger.error(f"Агент {agent_type} не найден: {e}")
            # Обновляем трассировку для fallback
            decision_trace["selected_agent"] = "default"
            decision_trace["reasoning"] = f"Fallback: агент {agent_type} не найден"
            decision_trace["error"] = str(e)
            
            # Fallback к default агенту
            from app.services.agents.default_agent import DefaultAgent
            agent = DefaultAgent()
            response = await agent.process(user_input, classification)
            
            # Завершаем трассировку для fallback
            end_time = datetime.now()
            decision_trace["end_time"] = end_time.isoformat()
            decision_trace["processing_time_ms"] = int((end_time - start_time).total_seconds() * 1000)
            
            if response.metadata is None:
                response.metadata = {}
            response.metadata["decision_trace"] = decision_trace
            
            return response
        except Exception as e:
            # Добавляем ошибку в трассировку
            end_time = datetime.now()
            decision_trace["end_time"] = end_time.isoformat()
            decision_trace["processing_time_ms"] = int((end_time - start_time).total_seconds() * 1000)
            decision_trace["error"] = str(e)
            
            logger.error(f"Ошибка при обработке агентом {agent_type}: {e}")
            raise
    
    async def coordinate_agents(
        self, 
        initial_response: AgentResponse,
        user_input: str,
        next_agent_types: List[str]
    ) -> List[AgentResponse]:
        """
        Координирует работу нескольких агентов для выполнения сложных задач.
        
        Args:
            initial_response: Ответ первого агента
            user_input: Исходное сообщение пользователя
            next_agent_types: Список типов агентов для следующего шага
            
        Returns:
            Список ответов от агентов в цепочке
        """
        chain_responses = []
        
        for agent_type in next_agent_types:
            try:
                logger.info(f"Запуск агента {agent_type} в цепочке...")
                
                # Создаем классификацию для следующего агента
                # Передаем метаданные из предыдущего агента как extracted_data
                classification = IntentClassification(
                    agent_type=agent_type,
                    confidence=1.0,
                    extracted_data={
                        **initial_response.metadata,
                        "chain_source": initial_response.agent_type
                    },
                    reasoning=f"Запуск в цепочке после {initial_response.agent_type}"
                )
                
                # Получаем агента
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
                chain_responses.append(response)
                
                # Обновляем user_input для следующего агента (может использовать результаты предыдущего)
                user_input = f"{user_input}\n\nКонтекст: {response.response[:200]}"
                
            except Exception as e:
                logger.error(f"Ошибка при запуске агента {agent_type} в цепочке: {e}")
                # Продолжаем цепочку даже при ошибке одного агента
                continue
        
        return chain_responses
