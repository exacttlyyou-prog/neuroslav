"""
E2E тесты для критических пользовательских сценариев.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.models.schemas import AgentResponse


@pytest.mark.asyncio
class TestMeetingFlow:
    """E2E тесты для полного цикла обработки встречи."""
    
    async def test_complete_meeting_flow(
        self,
        test_client: TestClient,
        test_db,
        sample_telegram_update,
        sample_meeting_transcript,
        mock_telegram_service,
        mock_ollama_service,
        mock_notion_service
    ):
        """Тест полного цикла: запись → обработка → подтверждение → Notion."""
        
        # Настраиваем моки
        mock_ollama_service.analyze_meeting.return_value = {
            "summary_md": "<b>Встреча по проекту TEST</b>. Обсудили презентацию и запуск в продакшн.",
            "participants": [
                {"name": "Иван Петров"},
                {"name": "Мария Сидорова"}
            ],
            "action_items": [
                {
                    "text": "Сделать презентацию",
                    "assignee": "Мария Сидорова", 
                    "deadline": "2024-01-26",
                    "priority": "High"
                }
            ],
            "key_decisions": [
                {
                    "title": "Запуск в продакшн",
                    "description": "Решили запустить на следующей неделе",
                    "impact": "Выход продукта на рынок"
                }
            ],
            "insights": ["Команда готова к запуску"],
            "next_steps": ["Подготовка к продакшну"],
            "projects": [{"key": "TEST"}],
            "meeting_date": "2024-01-25",
            "meeting_time": "14:00",
            "risk_assessment": ""
        }
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            with patch('app.services.agent_router.AgentRouter') as mock_router_class:
                mock_router = AsyncMock()
                mock_router_class.return_value = mock_router
                
                # Настройка мока для обработки встречи
                mock_router.classify.return_value = type('Classification', (), {
                    'agent_type': 'meeting',
                    'confidence': 0.95
                })()
                
                mock_router.route.return_value = AgentResponse(
                    agent_type='meeting',
                    response='Встреча проанализирована. Саммари готово.',
                    actions=[
                        {'type': 'meeting_processed'},
                        {'type': 'task_created'}
                    ],
                    success=True
                )
                
                with patch('app.services.ollama_service.OllamaService', return_value=mock_ollama_service):
                    with patch('app.services.notion_service.NotionService', return_value=mock_notion_service):
                        
                        # Шаг 1: Отправка транскрипции встречи
                        sample_telegram_update["message"]["text"] = f"Обработай последнюю встречу:\n\n{sample_meeting_transcript}"
                        
                        response1 = test_client.post(
                            "/api/telegram/webhook",
                            json=sample_telegram_update
                        )
                        
                        assert response1.status_code == 200
                        
                        # Проверяем что встреча была обработана
                        mock_router.classify.assert_called()
                        mock_router.route.assert_called()
                        
                        # Шаг 2: Подтверждение встречи
                        from app.db.models import Meeting
                        from sqlalchemy import select
                        
                        # Создаем встречу с pending_approval статусом
                        meeting = Meeting(
                            id='test-meeting-1',
                            summary='Встреча по проекту TEST',
                            participants=[{"name": "Иван Петров"}, {"name": "Мария Сидорова"}],
                            action_items=[{
                                "text": "Сделать презентацию",
                                "assignee": "Мария Сидорова",
                                "deadline": "2024-01-26", 
                                "priority": "High"
                            }],
                            status='pending_approval'
                        )
                        test_db.add(meeting)
                        await test_db.commit()
                        
                        # Отправляем подтверждение
                        sample_telegram_update["message"]["text"] = "ок"
                        
                        response2 = test_client.post(
                            "/api/telegram/webhook", 
                            json=sample_telegram_update
                        )
                        
                        assert response2.status_code == 200
                        
                        # Проверяем что встреча была добавлена в Notion
                        mock_notion_service.create_meeting_in_db.assert_called_once()
                        
                        call_args = mock_notion_service.create_meeting_in_db.call_args
                        assert call_args[1]['meeting_id'] == 'test-meeting-1'
                        assert call_args[1]['title'].startswith('Встреча')
                        assert call_args[1]['summary'] == 'Встреча по проекту TEST'
                        
                        # Проверяем статус встречи в БД
                        result = await test_db.execute(
                            select(Meeting).where(Meeting.id == 'test-meeting-1')
                        )
                        updated_meeting = result.scalar_one()
                        assert updated_meeting.status == 'approved'
        
        # Проверяем все отправленные сообщения
        calls = mock_telegram_service.send_message_to_user.call_args_list
        
        # Должен быть автоответ + ответ обработки + подтверждение
        assert len(calls) >= 3
        
        # Проверяем подтверждение
        confirmation_found = any(
            "Встреча добавлена в Notion" in call[1]['message']
            for call in calls
        )
        assert confirmation_found


@pytest.mark.asyncio 
class TestTaskCreationFlow:
    """E2E тесты для создания задач."""
    
    async def test_task_creation_with_context(
        self,
        test_client: TestClient,
        test_db,
        sample_telegram_update,
        mock_telegram_service,
        mock_context_loader
    ):
        """Тест создания задачи с контекстом из базы знаний."""
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            with patch('app.services.agent_router.AgentRouter') as mock_router_class:
                mock_router = AsyncMock()
                mock_router_class.return_value = mock_router
                
                mock_router.classify.return_value = type('Classification', (), {
                    'agent_type': 'task',
                    'confidence': 0.95,
                    'extracted_data': {
                        'task_text': 'Сделать презентацию',
                        'assignee': 'testuser',
                        'deadline': '2024-01-26',
                        'priority': 'High'
                    }
                })()
                
                mock_router.route.return_value = AgentResponse(
                    agent_type='task',
                    response='Задача создана. Ответственный: Тестовый Пользователь. Дедлайн: пятница.',
                    actions=[{'type': 'task_created', 'task_id': 'task-123'}],
                    success=True
                )
                
                # Отправляем запрос на создание задачи
                sample_telegram_update["message"]["text"] = "testuser должен сделать презентацию к пятнице"
                
                response = test_client.post(
                    "/api/telegram/webhook",
                    json=sample_telegram_update  
                )
                
                assert response.status_code == 200
                
                # Проверяем что AgentRouter был вызван
                mock_router.classify.assert_called_once()
                mock_router.route.assert_called_once()
                
                # Проверяем отправленные сообщения
                calls = mock_telegram_service.send_message_to_user.call_args_list
                
                # Должен быть автоответ + результат + действия
                assert len(calls) >= 3
                
                # Проверяем результат обработки
                result_message = calls[1][1]['message']  # Второе сообщение - результат
                assert "Задача создана" in result_message
                assert "Тестовый Пользователь" in result_message
                
                # Проверяем действия
                actions_message = calls[2][1]['message']
                assert "📋 Задача создана" in actions_message


@pytest.mark.asyncio
class TestKnowledgeManagementFlow:
    """E2E тесты для управления знаниями."""
    
    async def test_save_and_retrieve_knowledge(
        self,
        test_client: TestClient,
        sample_telegram_update,
        mock_telegram_service,
        mock_rag_service
    ):
        """Тест сохранения и поиска информации в базе знаний."""
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            with patch('app.services.agent_router.AgentRouter') as mock_router_class:
                mock_router = AsyncMock()
                mock_router_class.return_value = mock_router
                
                # Шаг 1: Сохранение информации
                mock_router.classify.return_value = type('Classification', (), {
                    'agent_type': 'knowledge',
                    'confidence': 0.9
                })()
                
                mock_router.route.return_value = AgentResponse(
                    agent_type='knowledge',
                    response='Информация сохранена в базе знаний.',
                    actions=[{'type': 'knowledge_saved'}],
                    success=True
                )
                
                # Сохраняем информацию
                sample_telegram_update["message"]["text"] = "Запомни: проект TEST использует микросервисную архитектуру"
                
                response1 = test_client.post(
                    "/api/telegram/webhook",
                    json=sample_telegram_update
                )
                
                assert response1.status_code == 200
                
                # Шаг 2: Поиск информации  
                mock_router.classify.return_value = type('Classification', (), {
                    'agent_type': 'rag_query',
                    'confidence': 0.9
                })()
                
                mock_router.route.return_value = AgentResponse(
                    agent_type='rag_query', 
                    response='Проект TEST использует микросервисную архитектуру.',
                    actions=[{'type': 'search_completed'}],
                    success=True
                )
                
                # Ищем информацию
                sample_telegram_update["message"]["text"] = "Найди информацию о проекте TEST"
                
                response2 = test_client.post(
                    "/api/telegram/webhook",
                    json=sample_telegram_update
                )
                
                assert response2.status_code == 200
                
                # Проверяем что оба запроса были обработаны
                assert mock_router.classify.call_count == 2
                assert mock_router.route.call_count == 2
                
                # Проверяем результаты
                all_calls = mock_telegram_service.send_message_to_user.call_args_list
                
                # Ищем сообщения с результатами
                knowledge_saved = any(
                    "сохранена в базе знаний" in call[1]['message'].lower()
                    for call in all_calls
                )
                assert knowledge_saved
                
                knowledge_found = any(
                    "микросервисную архитектуру" in call[1]['message']
                    for call in all_calls 
                )
                assert knowledge_found


@pytest.mark.asyncio
class TestErrorRecoveryFlow:
    """E2E тесты для восстановления после ошибок."""
    
    async def test_ollama_service_fallback(
        self,
        test_client: TestClient,
        sample_telegram_update,
        mock_telegram_service
    ):
        """Тест fallback при недоступности Ollama."""
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            # Заставляем Ollama выбросить ошибку
            with patch('app.services.agent_router.AgentRouter') as mock_router_class:
                mock_router = AsyncMock()
                mock_router_class.return_value = mock_router
                
                # Классификация работает, но route падает
                mock_router.classify.return_value = type('Classification', (), {
                    'agent_type': 'default',
                    'confidence': 0.5
                })()
                
                mock_router.route.side_effect = Exception("Ollama недоступна")
                
                sample_telegram_update["message"]["text"] = "работаешь?"
                
                response = test_client.post(
                    "/api/telegram/webhook",
                    json=sample_telegram_update
                )
                
                assert response.status_code == 200
                
                # Проверяем что было отправлено сообщение об ошибке
                calls = mock_telegram_service.send_message_to_user.call_args_list
                
                error_message_found = any(
                    "ошибка" in call[1]['message'].lower()
                    for call in calls
                )
                assert error_message_found
    
    async def test_notion_service_fallback(
        self,
        test_client: TestClient,
        test_db,
        sample_telegram_update,
        mock_telegram_service
    ):
        """Тест fallback при недоступности Notion."""
        
        # Создаем встречу для подтверждения
        from app.db.models import Meeting
        
        meeting = Meeting(
            id='test-meeting-notion-fail',
            summary='Тестовая встреча',
            participants=[{"name": "Тест"}],
            action_items=[],
            status='pending_approval'
        )
        test_db.add(meeting)
        await test_db.commit()
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            # Заставляем NotionService выбросить ошибку
            with patch('app.services.notion_service.NotionService') as mock_notion_class:
                mock_notion = AsyncMock()
                mock_notion_class.return_value = mock_notion
                mock_notion.create_meeting_in_db.side_effect = Exception("Notion API недоступен")
                
                sample_telegram_update["message"]["text"] = "ок"
                
                response = test_client.post(
                    "/api/telegram/webhook",
                    json=sample_telegram_update
                )
                
                assert response.status_code == 200
                
                # Проверяем что отправлено сообщение об ошибке
                calls = mock_telegram_service.send_message_to_user.call_args_list
                
                error_found = any(
                    "пошло не так" in call[1]['message'] or 
                    "ошибка" in call[1]['message'].lower()
                    for call in calls
                )
                assert error_found
    
    async def test_graceful_degradation_multiple_failures(
        self,
        test_client: TestClient,
        sample_telegram_update,
        mock_telegram_service
    ):
        """Тест graceful degradation при множественных сбоях."""
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            # Все сервисы падают
            with patch('app.services.agent_router.AgentRouter') as mock_router_class:
                mock_router_class.side_effect = Exception("AgentRouter критическая ошибка")
                
                sample_telegram_update["message"]["text"] = "тестовое сообщение"
                
                response = test_client.post(
                    "/api/telegram/webhook",
                    json=sample_telegram_update
                )
                
                # Webhook должен всегда возвращать 200
                assert response.status_code == 200
                
                # Но должен был отправить автоответ перед падением
                calls = mock_telegram_service.send_message_to_user.call_args_list
                assert len(calls) >= 1  # Хотя бы автоответ должен быть отправлен