"""
Конфигурация структурированного логирования с correlation IDs.
"""
import sys
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from loguru import logger

# Context variable для хранения correlation ID в рамках запроса
correlation_id_context: ContextVar[str] = ContextVar('correlation_id', default='')
user_context: ContextVar[Dict[str, Any]] = ContextVar('user_context', default={})
operation_context: ContextVar[Dict[str, Any]] = ContextVar('operation_context', default={})


class StructuredFormatter:
    """Форматтер для структурированного JSON логирования."""
    
    def __init__(self, include_extra: bool = True):
        self.include_extra = include_extra
    
    def format(self, record: Dict[str, Any]) -> str:
        """Форматирует лог-запись в JSON."""
        # Базовые поля
        log_entry = {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "message": record["message"],
            "logger": record["name"],
            "module": record["module"],
            "function": record["function"],
            "line": record["line"],
        }
        
        # Добавляем correlation ID если есть
        correlation_id = correlation_id_context.get('')
        if correlation_id:
            log_entry["correlation_id"] = correlation_id
        
        # Добавляем пользовательский контекст
        user_ctx = user_context.get({})
        if user_ctx:
            log_entry["user"] = user_ctx
        
        # Добавляем контекст операции
        op_ctx = operation_context.get({})
        if op_ctx:
            log_entry["operation"] = op_ctx
        
        # Добавляем exception информацию
        if record.get("exception"):
            log_entry["exception"] = {
                "type": record["exception"].type.__name__ if record["exception"].type else None,
                "value": str(record["exception"].value) if record["exception"].value else None,
                "traceback": record["exception"].traceback if record["exception"].traceback else None
            }
        
        # Добавляем дополнительные поля
        if self.include_extra and "extra" in record:
            extra = record["extra"]
            if isinstance(extra, dict):
                # Фильтруем системные поля loguru
                filtered_extra = {
                    k: v for k, v in extra.items() 
                    if not k.startswith('_') and k not in log_entry
                }
                log_entry.update(filtered_extra)
        
        # Добавляем служебные метаданные
        log_entry["source"] = "digital_twin_api"
        log_entry["environment"] = "production"  # Можно вынести в конфиг
        
        return json.dumps(log_entry, ensure_ascii=False, default=str)


class CorrelationLogger:
    """Обертка для логгера с поддержкой correlation ID."""
    
    def __init__(self):
        self._logger = logger
        
    def bind_correlation(self, correlation_id: str = None) -> 'CorrelationLogger':
        """Привязывает correlation ID к логгеру."""
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())
        
        correlation_id_context.set(correlation_id)
        return self
    
    def bind_user(self, user_id: str = None, chat_id: str = None, **kwargs) -> 'CorrelationLogger':
        """Привязывает пользовательский контекст."""
        user_ctx = {
            "user_id": user_id,
            "chat_id": chat_id,
            **kwargs
        }
        # Удаляем None значения
        user_ctx = {k: v for k, v in user_ctx.items() if v is not None}
        user_context.set(user_ctx)
        return self
    
    def bind_operation(self, operation: str, **kwargs) -> 'CorrelationLogger':
        """Привязывает контекст операции."""
        op_ctx = {
            "operation": operation,
            **kwargs
        }
        operation_context.set(op_ctx)
        return self
    
    def info(self, message: str, **kwargs):
        """Логирует информационное сообщение."""
        self._logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Логирует предупреждение."""
        self._logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Логирует ошибку."""
        self._logger.error(message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """Логирует отладочное сообщение."""
        self._logger.debug(message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Логирует критическую ошибку."""
        self._logger.critical(message, **kwargs)


class LoggingConfig:
    """Конфигурация системы логирования."""
    
    def __init__(
        self,
        log_level: str = "INFO",
        log_dir: str = "logs",
        structured: bool = True,
        console_output: bool = True,
        file_output: bool = True,
        rotation: str = "1 day",
        retention: str = "30 days"
    ):
        self.log_level = log_level
        self.log_dir = Path(log_dir)
        self.structured = structured
        self.console_output = console_output
        self.file_output = file_output
        self.rotation = rotation
        self.retention = retention
        
        # Создаем директорию для логов
        self.log_dir.mkdir(exist_ok=True)
    
    def setup_logging(self):
        """Настраивает систему логирования."""
        # Удаляем стандартный обработчик loguru
        logger.remove()
        
        formatter = StructuredFormatter() if self.structured else None
        
        # Консольный вывод
        if self.console_output:
            if self.structured:
                logger.add(
                    sys.stdout,
                    format=formatter.format,
                    level=self.log_level,
                    colorize=False,
                    serialize=False
                )
            else:
                logger.add(
                    sys.stdout,
                    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                    level=self.log_level,
                    colorize=True
                )
        
        # Файловый вывод
        if self.file_output:
            # Основной лог
            main_log = self.log_dir / "digital_twin.log"
            if self.structured:
                logger.add(
                    str(main_log),
                    format=formatter.format,
                    level=self.log_level,
                    rotation=self.rotation,
                    retention=self.retention,
                    compression="gz",
                    serialize=False
                )
            else:
                logger.add(
                    str(main_log),
                    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                    level=self.log_level,
                    rotation=self.rotation,
                    retention=self.retention,
                    compression="gz"
                )
            
            # Лог ошибок
            error_log = self.log_dir / "errors.log"
            logger.add(
                str(error_log),
                format=formatter.format if self.structured else "{time} | {level} | {message}",
                level="ERROR",
                rotation=self.rotation,
                retention=self.retention,
                compression="gz",
                filter=lambda record: record["level"].name in ["ERROR", "CRITICAL"]
            )
            
            # Лог безопасности
            security_log = self.log_dir / "security.log"
            logger.add(
                str(security_log),
                format=formatter.format if self.structured else "{time} | {level} | {message}",
                level="INFO",
                rotation=self.rotation,
                retention=self.retention,
                compression="gz",
                filter=lambda record: "security" in record.get("extra", {})
            )
            
            # Лог производительности
            performance_log = self.log_dir / "performance.log"
            logger.add(
                str(performance_log),
                format=formatter.format if self.structured else "{time} | {level} | {message}",
                level="INFO",
                rotation="100 MB",  # Производительность может генерировать много логов
                retention=self.retention,
                compression="gz",
                filter=lambda record: "performance" in record.get("extra", {})
            )
        
        logger.info("Structured logging configured successfully")


@contextmanager
def log_context(correlation_id: str = None, **context):
    """Context manager для установки контекста логирования."""
    # Сохраняем текущий контекст
    old_correlation = correlation_id_context.get('')
    old_user = user_context.get({})
    old_operation = operation_context.get({})
    
    try:
        # Устанавливаем новый контекст
        if correlation_id:
            correlation_id_context.set(correlation_id)
        
        if 'user_id' in context or 'chat_id' in context:
            user_ctx = {
                k: v for k, v in context.items() 
                if k in ['user_id', 'chat_id', 'username']
            }
            user_context.set({**old_user, **user_ctx})
        
        if 'operation' in context:
            op_ctx = {
                k: v for k, v in context.items()
                if k.startswith('operation') or k in ['service', 'endpoint']
            }
            operation_context.set({**old_operation, **op_ctx})
        
        yield
        
    finally:
        # Восстанавливаем старый контекст
        correlation_id_context.set(old_correlation)
        user_context.set(old_user)
        operation_context.set(old_operation)


def get_correlation_id() -> str:
    """Получает текущий correlation ID."""
    return correlation_id_context.get('')


def set_correlation_id(correlation_id: str):
    """Устанавливает correlation ID."""
    correlation_id_context.set(correlation_id)


def get_structured_logger() -> CorrelationLogger:
    """Получает структурированный логгер."""
    return CorrelationLogger()


class BusinessEventLogger:
    """Логгер для бизнес-событий."""
    
    def __init__(self):
        self.logger = get_structured_logger()
    
    def log_user_interaction(
        self,
        interaction_type: str,
        user_id: str = None,
        chat_id: str = None,
        details: Dict[str, Any] = None
    ):
        """Логирует взаимодействие пользователя."""
        self.logger.bind_user(user_id=user_id, chat_id=chat_id).info(
            f"User interaction: {interaction_type}",
            interaction_type=interaction_type,
            details=details or {},
            event_category="user_interaction"
        )
    
    def log_agent_execution(
        self,
        agent_type: str,
        user_input: str,
        response: str,
        success: bool,
        duration_ms: float,
        metadata: Dict[str, Any] = None
    ):
        """Логирует выполнение агента."""
        self.logger.bind_operation(operation="agent_execution").info(
            f"Agent executed: {agent_type}",
            agent_type=agent_type,
            user_input=user_input[:200] + "..." if len(user_input) > 200 else user_input,
            response_length=len(response),
            success=success,
            duration_ms=duration_ms,
            metadata=metadata or {},
            event_category="agent_execution"
        )
    
    def log_external_service_call(
        self,
        service: str,
        operation: str,
        success: bool,
        duration_ms: float,
        error: str = None
    ):
        """Логирует вызов внешнего сервиса."""
        level = "info" if success else "error"
        getattr(self.logger, level)(
            f"External service call: {service}.{operation}",
            service=service,
            operation=operation,
            success=success,
            duration_ms=duration_ms,
            error=error,
            event_category="external_service"
        )
    
    def log_business_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        user_context: Dict[str, Any] = None
    ):
        """Логирует произвольное бизнес-событие."""
        self.logger.info(
            f"Business event: {event_type}",
            event_type=event_type,
            event_data=event_data,
            user_context=user_context or {},
            event_category="business_event"
        )


# Глобальные экземпляры
_business_logger: Optional[BusinessEventLogger] = None


def get_business_logger() -> BusinessEventLogger:
    """Получает бизнес-логгер."""
    global _business_logger
    if _business_logger is None:
        _business_logger = BusinessEventLogger()
    return _business_logger


def setup_production_logging():
    """Настраивает логирование для продакшена."""
    config = LoggingConfig(
        log_level="INFO",
        structured=True,
        console_output=True,
        file_output=True,
        rotation="1 day",
        retention="30 days"
    )
    config.setup_logging()


def setup_development_logging():
    """Настраивает логирование для разработки."""
    config = LoggingConfig(
        log_level="DEBUG",
        structured=False,  # Человекочитаемый формат для разработки
        console_output=True,
        file_output=False,  # В разработке можно не сохранять в файлы
    )
    config.setup_logging()


# Декораторы для автоматического логирования
def log_function_call(operation_name: str = None):
    """Декоратор для автоматического логирования вызовов функций."""
    def decorator(func):
        import functools
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            correlation_id = get_correlation_id() or str(uuid.uuid4())
            
            with log_context(
                correlation_id=correlation_id,
                operation=op_name,
                function=func.__name__,
                module=func.__module__
            ):
                start_time = datetime.now()
                try:
                    logger.debug(f"Starting function: {op_name}")
                    result = await func(*args, **kwargs)
                    duration = (datetime.now() - start_time).total_seconds() * 1000
                    logger.debug(f"Function completed: {op_name}", duration_ms=duration)
                    return result
                except Exception as e:
                    duration = (datetime.now() - start_time).total_seconds() * 1000
                    logger.error(
                        f"Function failed: {op_name}",
                        error=str(e),
                        duration_ms=duration,
                        exception_type=type(e).__name__
                    )
                    raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            correlation_id = get_correlation_id() or str(uuid.uuid4())
            
            with log_context(
                correlation_id=correlation_id,
                operation=op_name,
                function=func.__name__,
                module=func.__module__
            ):
                start_time = datetime.now()
                try:
                    logger.debug(f"Starting function: {op_name}")
                    result = func(*args, **kwargs)
                    duration = (datetime.now() - start_time).total_seconds() * 1000
                    logger.debug(f"Function completed: {op_name}", duration_ms=duration)
                    return result
                except Exception as e:
                    duration = (datetime.now() - start_time).total_seconds() * 1000
                    logger.error(
                        f"Function failed: {op_name}",
                        error=str(e),
                        duration_ms=duration,
                        exception_type=type(e).__name__
                    )
                    raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator