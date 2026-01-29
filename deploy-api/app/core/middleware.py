"""
Middleware для обработки ошибок, логирования и безопасности.
"""
import time
import uuid
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

from app.core.errors import (
    BaseDigitalTwinError, 
    ErrorSeverity, 
    get_error_tracker,
    ConfigurationError
)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware для централизованной обработки ошибок."""
    
    async def dispatch(self, request: Request, call_next):
        """Обрабатывает запрос с отслеживанием ошибок."""
        # Генерируем correlation ID для отслеживания запроса
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Логируем успешный запрос
            process_time = time.time() - start_time
            logger.info(
                f"Request completed",
                extra={
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "url": str(request.url),
                    "status_code": response.status_code,
                    "process_time": round(process_time, 3)
                }
            )
            
            # Добавляем correlation ID в заголовки ответа
            response.headers["X-Correlation-ID"] = correlation_id
            
            return response
            
        except BaseDigitalTwinError as e:
            # Обрабатываем наши кастомные ошибки
            error_tracker = get_error_tracker()
            error_tracker.track_error(e)
            
            # Определяем HTTP статус на основе severity
            status_code = self._get_status_code_from_severity(e.severity)
            
            logger.error(
                f"Digital Twin error: {e.message}",
                extra={
                    "correlation_id": correlation_id,
                    "error_details": e.to_dict()
                }
            )
            
            return JSONResponse(
                status_code=status_code,
                content={
                    "error": True,
                    "message": e.user_message,
                    "details": e.message if e.severity != ErrorSeverity.CRITICAL else None,
                    "correlation_id": correlation_id,
                    "service": e.service_type.value if e.service_type else None
                },
                headers={"X-Correlation-ID": correlation_id}
            )
            
        except HTTPException as e:
            # Обрабатываем стандартные HTTP ошибки FastAPI
            logger.warning(
                f"HTTP exception: {e.detail}",
                extra={
                    "correlation_id": correlation_id,
                    "status_code": e.status_code
                }
            )
            
            # Пропускаем HTTP исключения дальше
            raise
            
        except Exception as e:
            # Обрабатываем неожиданные ошибки
            logger.error(
                f"Unexpected error: {str(e)}",
                extra={
                    "correlation_id": correlation_id,
                    "error_type": type(e).__name__,
                    "traceback": logger.catch
                }
            )
            
            # Создаем общую ошибку
            digital_twin_error = BaseDigitalTwinError(
                message=f"Unexpected error: {str(e)}",
                severity=ErrorSeverity.CRITICAL,
                context={"request_path": str(request.url)},
                original_exception=e
            )
            
            error_tracker = get_error_tracker()
            error_tracker.track_error(digital_twin_error)
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": True,
                    "message": "Произошла неожиданная ошибка. Администратор уведомлен.",
                    "correlation_id": correlation_id
                },
                headers={"X-Correlation-ID": correlation_id}
            )
    
    def _get_status_code_from_severity(self, severity: ErrorSeverity) -> int:
        """Преобразует severity в HTTP статус код."""
        severity_to_status = {
            ErrorSeverity.LOW: 400,        # Bad Request
            ErrorSeverity.MEDIUM: 422,     # Unprocessable Entity
            ErrorSeverity.HIGH: 503,       # Service Unavailable
            ErrorSeverity.CRITICAL: 500,   # Internal Server Error
        }
        return severity_to_status.get(severity, 500)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware для ограничения частоты запросов."""
    
    def __init__(self, app, calls_per_minute: int = 60):
        super().__init__(app)
        self.calls_per_minute = calls_per_minute
        self.request_counts: Dict[str, Dict] = {}
    
    async def dispatch(self, request: Request, call_next):
        """Проверяет лимиты запросов."""
        # Telegram webhook — все запросы с одних IP Telegram; лимит по IP режет легитимный трафик
        if "/api/telegram/webhook" in str(request.url.path):
            return await call_next(request)

        client_id = self._get_client_id(request)
        if await self._is_rate_limited(client_id):
            return JSONResponse(
                status_code=429,
                content={
                    "error": True,
                    "message": "Слишком много запросов. Повторите через минуту.",
                    "retry_after": 60
                }
            )
        
        # Записываем запрос
        await self._record_request(client_id)
        
        return await call_next(request)
    
    def _get_client_id(self, request: Request) -> str:
        """Получает идентификатор клиента для rate limiting."""
        # Для Telegram webhook используем chat_id из тела запроса
        if "/telegram/webhook" in str(request.url):
            try:
                # Читаем body (осторожно, можно прочитать только один раз)
                # В продакшне лучше использовать IP
                return request.client.host if request.client else "unknown"
            except:
                pass
        
        # Для остальных API используем IP
        return request.client.host if request.client else "unknown"
    
    async def _is_rate_limited(self, client_id: str) -> bool:
        """Проверяет превышение лимита запросов."""
        current_time = time.time()
        
        if client_id not in self.request_counts:
            return False
        
        client_data = self.request_counts[client_id]
        
        # Очищаем старые запросы (старше 1 минуты)
        client_data["requests"] = [
            req_time for req_time in client_data["requests"]
            if current_time - req_time < 60
        ]
        
        # Проверяем лимит
        return len(client_data["requests"]) >= self.calls_per_minute
    
    async def _record_request(self, client_id: str):
        """Записывает запрос для rate limiting."""
        current_time = time.time()
        
        if client_id not in self.request_counts:
            self.request_counts[client_id] = {"requests": []}
        
        self.request_counts[client_id]["requests"].append(current_time)
    
    def get_client_stats(self) -> Dict[str, Any]:
        """Возвращает статистику по клиентам."""
        stats = {}
        current_time = time.time()
        
        for client_id, data in self.request_counts.items():
            recent_requests = [
                req for req in data["requests"]
                if current_time - req < 60
            ]
            stats[client_id] = {
                "requests_last_minute": len(recent_requests),
                "is_rate_limited": len(recent_requests) >= self.calls_per_minute
            }
        
        return stats


class RequestTracking:
    """Утилиты для отслеживания запросов."""
    
    @staticmethod
    def get_correlation_id(request: Request) -> Optional[str]:
        """Получает correlation ID из запроса."""
        return getattr(request.state, 'correlation_id', None)
    
    @staticmethod
    @asynccontextmanager
    async def track_operation(operation_name: str, correlation_id: str = None):
        """Context manager для отслеживания операций."""
        start_time = time.time()
        op_id = correlation_id or str(uuid.uuid4())
        
        logger.info(
            f"Starting operation: {operation_name}",
            extra={"correlation_id": op_id, "operation": operation_name}
        )
        
        try:
            yield op_id
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Operation failed: {operation_name}",
                extra={
                    "correlation_id": op_id,
                    "operation": operation_name,
                    "duration": round(duration, 3),
                    "error": str(e)
                }
            )
            raise
        else:
            duration = time.time() - start_time
            logger.info(
                f"Operation completed: {operation_name}",
                extra={
                    "correlation_id": op_id,
                    "operation": operation_name, 
                    "duration": round(duration, 3)
                }
            )


def neural_slav_error_message(error: BaseDigitalTwinError) -> str:
    """Преобразует ошибку в сообщение в стиле Neural Slav."""
    
    if error.service_type == ServiceType.OLLAMA:
        messages = [
            "ИИ решил взять выходной. Работаю без него.",
            "Нейросеть ушла в отпуск. Временно замещаю.",
            "Оллама зависла. Что ж, буду отвечать сам.",
        ]
    elif error.service_type == ServiceType.NOTION:
        messages = [
            "Notion лежит. Записал на салфетке.",
            "Заметочник недоступен. Держу в уме.",
            "Notion не отвечает. Запомнил по старинке.",
        ]
    elif error.service_type == ServiceType.TELEGRAM:
        messages = [
            "Телеграм молчит. Крик в пустоту записан.",
            "Боты забастовали. Сообщение принято к сведению.",
            "Telegram API лежит. Мысленно отправил.",
        ]
    elif error.service_type == ServiceType.DATABASE:
        messages = [
            "База данных ушла курить. Держу в голове.",
            "SQL-сервер решил поспать. Записал на память.",
            "БД недоступна. Старая школа - блокнот и ручка.",
        ]
    else:
        messages = [
            "Что-то сломалось. Но я справлюсь.",
            "Техника подводит. Человеческий фактор рулит.",
            "Ошибка в матрице. Работаю в автономном режиме.",
        ]
    
    import random
    return random.choice(messages)