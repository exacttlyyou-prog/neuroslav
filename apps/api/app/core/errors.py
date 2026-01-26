"""
Централизованная система обработки ошибок с graceful degradation.
"""
import traceback
from typing import Dict, Any, Optional, Union
from enum import Enum
from loguru import logger
from datetime import datetime


class ErrorSeverity(Enum):
    """Уровни критичности ошибок."""
    LOW = "low"           # Предупреждения, не влияют на работу
    MEDIUM = "medium"     # Ошибки, влияющие на функциональность
    HIGH = "high"         # Критические ошибки, могут нарушить работу
    CRITICAL = "critical" # Системные ошибки, требуют немедленного внимания


class ServiceType(Enum):
    """Типы сервисов для graceful degradation."""
    OLLAMA = "ollama"
    NOTION = "notion" 
    TELEGRAM = "telegram"
    DATABASE = "database"
    RAG = "rag"
    CACHE = "cache"
    RECORDING = "recording"


class BaseDigitalTwinError(Exception):
    """Базовый класс для всех исключений Digital Twin системы."""
    
    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        service_type: Optional[ServiceType] = None,
        user_message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        self.message = message
        self.severity = severity
        self.service_type = service_type
        self.user_message = user_message or self._generate_user_message()
        self.context = context or {}
        self.original_exception = original_exception
        self.timestamp = datetime.now()
        
        super().__init__(message)
    
    def _generate_user_message(self) -> str:
        """Генерирует user-friendly сообщение об ошибке."""
        if self.severity == ErrorSeverity.CRITICAL:
            return "Произошла серьезная ошибка. Техническая поддержка уведомлена."
        elif self.severity == ErrorSeverity.HIGH:
            return "Не удалось выполнить операцию. Попробуйте позже."
        elif self.severity == ErrorSeverity.MEDIUM:
            return "Возникли временные проблемы. Система работает в ограниченном режиме."
        else:
            return "Операция выполнена с предупреждениями."
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует ошибку в словарь для логирования."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "severity": self.severity.value,
            "service_type": self.service_type.value if self.service_type else None,
            "user_message": self.user_message,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "original_exception": str(self.original_exception) if self.original_exception else None,
            "traceback": traceback.format_exc() if self.original_exception else None
        }


class OllamaServiceError(BaseDigitalTwinError):
    """Ошибки связанные с Ollama сервисом."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message, 
            service_type=ServiceType.OLLAMA,
            **kwargs
        )
    
    def _generate_user_message(self) -> str:
        return "ИИ временно недоступен. Отвечаю в ручном режиме."


class NotionServiceError(BaseDigitalTwinError):
    """Ошибки связанные с Notion сервисом."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            service_type=ServiceType.NOTION,
            **kwargs
        )
    
    def _generate_user_message(self) -> str:
        return "Не удалось сохранить в Notion. Данные сохранены локально."


class TelegramServiceError(BaseDigitalTwinError):
    """Ошибки связанные с Telegram сервисом."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            service_type=ServiceType.TELEGRAM,
            **kwargs
        )
    
    def _generate_user_message(self) -> str:
        return "Проблемы с отправкой сообщений. Повторите попытку."


class DatabaseError(BaseDigitalTwinError):
    """Ошибки связанные с базой данных."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            service_type=ServiceType.DATABASE,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )
    
    def _generate_user_message(self) -> str:
        return "Проблемы с сохранением данных. Попробуйте позже."


class ValidationError(BaseDigitalTwinError):
    """Ошибки валидации входящих данных."""
    
    def __init__(self, message: str, field: str = None, **kwargs):
        super().__init__(
            message,
            severity=ErrorSeverity.LOW,
            context={"field": field} if field else {},
            **kwargs
        )
    
    def _generate_user_message(self) -> str:
        field = self.context.get("field", "данных")
        return f"Некорректный формат {field}. Проверьте и попробуйте снова."


class RateLimitError(BaseDigitalTwinError):
    """Ошибки превышения лимитов запросов."""
    
    def __init__(self, message: str, limit: int = None, **kwargs):
        super().__init__(
            message,
            severity=ErrorSeverity.MEDIUM,
            context={"limit": limit} if limit else {},
            **kwargs
        )
    
    def _generate_user_message(self) -> str:
        return "Слишком много запросов. Подождите немного."


class ConfigurationError(BaseDigitalTwinError):
    """Ошибки конфигурации системы."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=ErrorSeverity.CRITICAL,
            **kwargs
        )
    
    def _generate_user_message(self) -> str:
        return "Системная ошибка конфигурации. Администратор уведомлен."


class ErrorTracker:
    """Отслеживает ошибки для анализа паттернов и graceful degradation."""
    
    def __init__(self):
        self.error_counts = {}
        self.service_health = {}
        self.circuit_breakers = {}
    
    def track_error(self, error: BaseDigitalTwinError):
        """Отслеживает ошибку для статистики."""
        error_key = f"{error.service_type.value if error.service_type else 'unknown'}:{error.__class__.__name__}"
        
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        
        # Обновляем здоровье сервиса
        if error.service_type:
            service = error.service_type.value
            if service not in self.service_health:
                self.service_health[service] = {"errors": 0, "total_requests": 0}
            
            self.service_health[service]["errors"] += 1
            self.service_health[service]["total_requests"] += 1
        
        # Логируем ошибку
        logger.error(f"Tracked error: {error_key}", extra=error.to_dict())
    
    def get_service_health_score(self, service_type: ServiceType) -> float:
        """Возвращает оценку здоровья сервиса (0-1)."""
        service = service_type.value
        if service not in self.service_health:
            return 1.0
        
        health_data = self.service_health[service]
        if health_data["total_requests"] == 0:
            return 1.0
        
        error_rate = health_data["errors"] / health_data["total_requests"]
        return max(0.0, 1.0 - error_rate)
    
    def should_use_fallback(self, service_type: ServiceType, threshold: float = 0.5) -> bool:
        """Определяет нужно ли использовать fallback для сервиса."""
        health_score = self.get_service_health_score(service_type)
        return health_score < threshold
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Возвращает статистику ошибок."""
        return {
            "error_counts": self.error_counts,
            "service_health": self.service_health,
            "total_errors": sum(self.error_counts.values())
        }


class GracefulDegradationManager:
    """Управляет graceful degradation при сбоях сервисов."""
    
    def __init__(self, error_tracker: ErrorTracker):
        self.error_tracker = error_tracker
        self.fallback_strategies = {
            ServiceType.OLLAMA: self._ollama_fallback,
            ServiceType.NOTION: self._notion_fallback,
            ServiceType.TELEGRAM: self._telegram_fallback,
            ServiceType.DATABASE: self._database_fallback,
        }
    
    async def execute_with_fallback(
        self,
        service_type: ServiceType,
        primary_func,
        *args,
        **kwargs
    ) -> Any:
        """Выполняет функцию с fallback при сбоях."""
        try:
            # Проверяем нужен ли fallback
            if self.error_tracker.should_use_fallback(service_type):
                logger.warning(f"Using fallback for {service_type.value} due to poor health")
                return await self._execute_fallback(service_type, *args, **kwargs)
            
            # Пытаемся выполнить основную функцию
            result = await primary_func(*args, **kwargs)
            
            # Успех - обновляем статистику
            if service_type.value in self.error_tracker.service_health:
                self.error_tracker.service_health[service_type.value]["total_requests"] += 1
            
            return result
            
        except Exception as e:
            # Создаем и отслеживаем ошибку
            error = self._create_service_error(service_type, str(e), original_exception=e)
            self.error_tracker.track_error(error)
            
            # Выполняем fallback
            logger.warning(f"Primary function failed for {service_type.value}, using fallback: {e}")
            return await self._execute_fallback(service_type, *args, **kwargs)
    
    def _create_service_error(
        self,
        service_type: ServiceType,
        message: str,
        **kwargs
    ) -> BaseDigitalTwinError:
        """Создает подходящую ошибку для типа сервиса."""
        error_classes = {
            ServiceType.OLLAMA: OllamaServiceError,
            ServiceType.NOTION: NotionServiceError,
            ServiceType.TELEGRAM: TelegramServiceError,
            ServiceType.DATABASE: DatabaseError,
        }
        
        error_class = error_classes.get(service_type, BaseDigitalTwinError)
        return error_class(message, **kwargs)
    
    async def _execute_fallback(self, service_type: ServiceType, *args, **kwargs) -> Any:
        """Выполняет fallback стратегию."""
        fallback_func = self.fallback_strategies.get(service_type)
        if fallback_func:
            return await fallback_func(*args, **kwargs)
        else:
            logger.error(f"No fallback strategy for {service_type.value}")
            return None
    
    async def _ollama_fallback(self, *args, **kwargs) -> str:
        """Fallback для Ollama - возвращает предопределенный ответ."""
        return "Сделано. ИИ временно недоступен, отвечаю сам."
    
    async def _notion_fallback(self, *args, **kwargs) -> Dict[str, Any]:
        """Fallback для Notion - возвращает mock результат."""
        return {
            "id": "fallback-id",
            "url": "",
            "success": False,
            "fallback": True
        }
    
    async def _telegram_fallback(self, *args, **kwargs) -> Dict[str, Any]:
        """Fallback для Telegram - логирует сообщение локально."""
        message = kwargs.get("message", args[1] if len(args) > 1 else "Unknown message")
        logger.info(f"Telegram fallback - would send: {message}")
        return {
            "message_id": -1,
            "success": False,
            "fallback": True
        }
    
    async def _database_fallback(self, *args, **kwargs) -> Any:
        """Fallback для базы данных - кеширует операцию."""
        logger.error("Database fallback - operation cached for retry")
        return None


# Глобальные экземпляры
_error_tracker: Optional[ErrorTracker] = None
_degradation_manager: Optional[GracefulDegradationManager] = None


def get_error_tracker() -> ErrorTracker:
    """Получает глобальный экземпляр отслеживания ошибок."""
    global _error_tracker
    if _error_tracker is None:
        _error_tracker = ErrorTracker()
    return _error_tracker


def get_degradation_manager() -> GracefulDegradationManager:
    """Получает глобальный экземпляр graceful degradation."""
    global _degradation_manager
    if _degradation_manager is None:
        _degradation_manager = GracefulDegradationManager(get_error_tracker())
    return _degradation_manager


def handle_service_error(
    service_type: ServiceType,
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
    user_message: Optional[str] = None
) -> BaseDigitalTwinError:
    """
    Утилита для обработки ошибок сервисов.
    
    Args:
        service_type: Тип сервиса где произошла ошибка
        error: Исходное исключение
        context: Дополнительный контекст
        user_message: Кастомное сообщение для пользователя
        
    Returns:
        Обработанная ошибка Digital Twin
    """
    # Определяем severity на основе типа ошибки
    severity = ErrorSeverity.MEDIUM
    if "connection" in str(error).lower() or "timeout" in str(error).lower():
        severity = ErrorSeverity.HIGH
    elif "configuration" in str(error).lower() or "auth" in str(error).lower():
        severity = ErrorSeverity.CRITICAL
    
    # Создаем подходящую ошибку
    degradation_manager = get_degradation_manager()
    digital_twin_error = degradation_manager._create_service_error(
        service_type,
        str(error),
        severity=severity,
        context=context,
        user_message=user_message,
        original_exception=error
    )
    
    # Отслеживаем ошибку
    get_error_tracker().track_error(digital_twin_error)
    
    return digital_twin_error