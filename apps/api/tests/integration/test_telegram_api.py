"""
Integration тесты для Telegram API endpoints.
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.models.schemas import AgentResponse


@pytest.mark.asyncio 
class TestTelegramWebhook:
    """Тесты для Telegram webhook endpoint."""
    
    async def test_webhook_basic_message(
        self,
        test_client: TestClient,
        sample_telegram_update,
        mock_telegram_service,
        mock_ollama_service
    ):
        """Тест базовой обработки сообщения через webhook."""
        
        # Мокаем сервисы
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            # Отправляем webhook
            response = test_client.post(
                "/api/telegram/webhook",
                json=sample_telegram_update
            )
        
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        
        # Проверяем что автоответ был отправлен
        mock_telegram_service.send_message_to_user.assert_called()
        
        # Получаем аргументы первого вызова
        call_args = mock_telegram_service.send_message_to_user.call_args
        assert call_args[1]['chat_id'] == '12345'
        assert len(call_args[1]['message']) > 0  # Автоответ не пустой
    
    async def test_webhook_command_start(
        self,
        test_client: TestClient,
        sample_telegram_update,
        mock_telegram_service
    ):
        """Тест команды /start."""
        
        # Модифицируем update для команды /start
        sample_telegram_update["message"]["text"] = "/start"
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            response = test_client.post(
                "/api/telegram/webhook", 
                json=sample_telegram_update
            )
        
        assert response.status_code == 200
        
        # Проверяем что отправлено приветственное сообщение
        mock_telegram_service.send_message_to_user.assert_called()
        call_args = mock_telegram_service.send_message_to_user.call_args
        message = call_args[1]['message']
        
        assert "Привет!" in message
        assert "Нейрослав" in message
        assert "/status" in message  # Должен содержать доступные команды
    
    async def test_webhook_command_health(
        self,
        test_client: TestClient,
        sample_telegram_update,
        mock_telegram_service,
        mock_ollama_service,
        mock_notion_service
    ):
        """Тест команды /health."""
        
        sample_telegram_update["message"]["text"] = "/health"
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            with patch('app.services.ollama_service.OllamaService', return_value=mock_ollama_service):
                with patch('app.services.notion_service.NotionService', return_value=mock_notion_service):
                    response = test_client.post(
                        "/api/telegram/webhook",
                        json=sample_telegram_update
                    )
        
        assert response.status_code == 200
        
        # Проверяем что отправлен health check
        assert mock_telegram_service.send_message_to_user.call_count >= 2  # Начальное + результат
        
        # Проверяем содержание последнего сообщения
        final_call = mock_telegram_service.send_message_to_user.call_args_list[-1]
        message = final_call[1]['message']
        
        assert "ОТЧЕТ О ЗДОРОВЬЕ СИСТЕМЫ" in message
        assert "Ollama:" in message
        assert "Notion:" in message
    
    async def test_webhook_approval_command(
        self,
        test_client: TestClient,
        test_db,
        sample_telegram_update,
        mock_telegram_service,
        mock_notion_service
    ):
        """Тест команды подтверждения встречи."""
        
        # Создаем встречу в БД со статусом pending_approval
        from app.db.models import Meeting
        from sqlalchemy.dialects.sqlite import insert
        
        meeting_data = {
            'id': 'test-meeting-id',
            'summary': 'Тестовое саммари встречи',
            'participants': [{'name': 'Тест Пользователь'}],
            'action_items': [{'text': 'Тестовая задача', 'assignee': 'Тест'}],
            'status': 'pending_approval'
        }
        
        stmt = insert(Meeting).values(**meeting_data)
        await test_db.execute(stmt)
        await test_db.commit()
        
        # Отправляем команду подтверждения
        sample_telegram_update["message"]["text"] = "ок"
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            with patch('app.services.notion_service.NotionService', return_value=mock_notion_service):
                response = test_client.post(
                    "/api/telegram/webhook",
                    json=sample_telegram_update
                )
        
        assert response.status_code == 200
        
        # Проверяем что встреча была добавлена в Notion
        mock_notion_service.create_meeting_in_db.assert_called_once()
        
        # Проверяем что отправлено подтверждение
        calls = mock_telegram_service.send_message_to_user.call_args_list
        confirmation_found = any(
            "Встреча добавлена в Notion" in call[1]['message']
            for call in calls
        )
        assert confirmation_found
    
    async def test_webhook_forwarded_message(
        self,
        test_client: TestClient,
        sample_telegram_update,
        mock_telegram_service
    ):
        """Тест обработки пересылаемого сообщения."""
        
        # Добавляем информацию о пересылке
        sample_telegram_update["message"]["forward_from"] = {
            "id": 98765,
            "first_name": "Forwarded",
            "username": "forwarded_user"
        }
        sample_telegram_update["message"]["forward_date"] = 1640990000
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            with patch('app.services.agent_router.AgentRouter') as mock_router_class:
                mock_router = AsyncMock()
                mock_router_class.return_value = mock_router
                
                mock_router.classify.return_value = type('Classification', (), {
                    'agent_type': 'knowledge',
                    'confidence': 0.9
                })()
                
                mock_router.route.return_value = AgentResponse(
                    agent_type='knowledge',
                    response='Информация сохранена в базе знаний',
                    actions=[{'type': 'knowledge_saved'}],
                    success=True
                )
                
                response = test_client.post(
                    "/api/telegram/webhook",
                    json=sample_telegram_update
                )
        
        assert response.status_code == 200
        
        # Проверяем что сообщение было обработано как пересылаемое
        mock_router.classify.assert_called_once()
        classify_call = mock_router.classify.call_args[0][0]
        assert "ПЕРЕСЫЛАЕМОЕ СООБЩЕНИЕ:" in classify_call
        assert "От пользователя: Forwarded (@forwarded_user)" in classify_call
    
    async def test_webhook_error_handling(
        self,
        test_client: TestClient,
        sample_telegram_update,
        mock_telegram_service
    ):
        """Тест обработки ошибок в webhook."""
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            # Заставляем AgentRouter выбросить ошибку
            with patch('app.services.agent_router.AgentRouter') as mock_router_class:
                mock_router = AsyncMock()
                mock_router_class.return_value = mock_router
                mock_router.classify.side_effect = Exception("Тестовая ошибка")
                
                response = test_client.post(
                    "/api/telegram/webhook",
                    json=sample_telegram_update
                )
        
        assert response.status_code == 200  # Webhook всегда возвращает 200
        
        # Проверяем что было отправлено сообщение об ошибке
        error_message_sent = any(
            "ошибка" in call[1]['message'].lower()
            for call in mock_telegram_service.send_message_to_user.call_args_list
        )
        assert error_message_sent
    
    async def test_webhook_empty_message(
        self,
        test_client: TestClient,
        mock_telegram_service
    ):
        """Тест обработки пустого сообщения."""
        
        update = {
            "update_id": 123,
            "message": None  # Пустое сообщение
        }
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            response = test_client.post(
                "/api/telegram/webhook",
                json=update
            )
        
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        
        # Не должно быть отправлено никаких сообщений
        mock_telegram_service.send_message_to_user.assert_not_called()


class TestTelegramRecording:
    """Тесты для команд записи встреч."""
    
    def test_start_recording_command(
        self,
        test_client: TestClient,
        sample_telegram_update,
        mock_telegram_service
    ):
        """Тест команды запуска записи."""
        
        sample_telegram_update["message"]["text"] = "запись"
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            with patch('app.services.recording_service.get_recording_service') as mock_recording:
                mock_recording.return_value.start_recording.return_value = True
                
                response = test_client.post(
                    "/api/telegram/webhook",
                    json=sample_telegram_update
                )
        
        assert response.status_code == 200
        
        # Проверяем что сервис записи был вызван
        mock_recording.return_value.start_recording.assert_called_once()
        
        # Проверяем сообщение о начале записи
        call_args = mock_telegram_service.send_message_to_user.call_args
        message = call_args[1]['message']
        assert "Запись встречи запущена" in message
    
    def test_stop_recording_command(
        self,
        test_client: TestClient,
        sample_telegram_update,
        mock_telegram_service
    ):
        """Тест команды остановки записи."""
        
        sample_telegram_update["message"]["text"] = "стоп"
        
        with patch('app.routers.telegram_webhook.DailyCheckinService') as mock_daily:
            mock_daily.return_value.telegram = mock_telegram_service
            
            with patch('app.services.recording_service.get_recording_service') as mock_recording:
                mock_recording.return_value.get_status.return_value = {'is_recording': True}
                
                response = test_client.post(
                    "/api/telegram/webhook",
                    json=sample_telegram_update
                )
        
        assert response.status_code == 200
        
        # Проверяем сообщение об остановке записи
        call_args = mock_telegram_service.send_message_to_user.call_args
        message = call_args[1]['message']
        assert "Останавливаю запись" in message