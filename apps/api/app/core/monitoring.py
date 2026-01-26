"""
Система мониторинга производительности (APM) для Digital Twin.
"""
import time
import psutil
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque
from loguru import logger


@dataclass
class PerformanceMetric:
    """Метрика производительности."""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = "count"


@dataclass 
class OperationTrace:
    """Трассировка операции."""
    operation_id: str
    operation_name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def finish(self, success: bool = True, error: str = None):
        """Завершает трассировку операции."""
        self.end_time = datetime.now()
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        self.success = success
        self.error = error


class MetricsCollector:
    """Сборщик метрик производительности."""
    
    def __init__(self, retention_hours: int = 24):
        self.retention_hours = retention_hours
        self.metrics: deque = deque()
        self.operation_traces: Dict[str, OperationTrace] = {}
        
        # Счетчики для быстрого доступа
        self.counters = defaultdict(int)
        self.histograms = defaultdict(list)
        
        # Системные метрики
        self.system_metrics = {}
    
    def record_metric(
        self,
        name: str,
        value: float,
        labels: Dict[str, str] = None,
        unit: str = "count"
    ):
        """Записывает метрику."""
        metric = PerformanceMetric(
            name=name,
            value=value,
            labels=labels or {},
            unit=unit
        )
        
        self.metrics.append(metric)
        self.counters[name] += 1
        
        # Ограничиваем размер коллекции
        if len(self.metrics) > 10000:
            self.metrics.popleft()
        
        # Добавляем в гистограммы для статистики
        self.histograms[name].append(value)
        if len(self.histograms[name]) > 1000:
            self.histograms[name].pop(0)
    
    def start_operation(self, operation_name: str, operation_id: str = None) -> str:
        """Начинает трассировку операции."""
        if not operation_id:
            operation_id = f"{operation_name}_{int(time.time()*1000)}"
        
        trace = OperationTrace(
            operation_id=operation_id,
            operation_name=operation_name,
            start_time=datetime.now()
        )
        
        self.operation_traces[operation_id] = trace
        return operation_id
    
    def finish_operation(
        self,
        operation_id: str,
        success: bool = True,
        error: str = None,
        metadata: Dict[str, Any] = None
    ):
        """Завершает трассировку операции."""
        if operation_id in self.operation_traces:
            trace = self.operation_traces[operation_id]
            trace.finish(success=success, error=error)
            
            if metadata:
                trace.metadata.update(metadata)
            
            # Записываем метрику времени выполнения
            self.record_metric(
                f"{trace.operation_name}_duration_ms",
                trace.duration_ms,
                labels={"success": str(success)},
                unit="milliseconds"
            )
            
            # Записываем метрику успеха/ошибки
            self.record_metric(
                f"{trace.operation_name}_total",
                1,
                labels={"success": str(success)},
                unit="count"
            )
            
            # Очищаем завершенную трассировку
            del self.operation_traces[operation_id]
    
    def get_operation_stats(self, operation_name: str) -> Dict[str, Any]:
        """Получает статистику по операции."""
        duration_metrics = [
            m for m in self.metrics 
            if m.name == f"{operation_name}_duration_ms"
        ]
        
        if not duration_metrics:
            return {"operation": operation_name, "stats": "no_data"}
        
        durations = [m.value for m in duration_metrics[-100:]]  # Последние 100
        
        total_metrics = [
            m for m in self.metrics
            if m.name == f"{operation_name}_total"
        ]
        
        success_count = sum(1 for m in total_metrics if m.labels.get("success") == "True")
        total_count = len(total_metrics)
        error_rate = ((total_count - success_count) / total_count) if total_count > 0 else 0
        
        return {
            "operation": operation_name,
            "total_calls": total_count,
            "success_rate": 1.0 - error_rate,
            "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
            "p95_duration_ms": self._percentile(durations, 0.95) if len(durations) > 5 else 0,
            "p99_duration_ms": self._percentile(durations, 0.99) if len(durations) > 10 else 0,
            "active_operations": len([t for t in self.operation_traces.values() if t.operation_name == operation_name])
        }
    
    def _percentile(self, values: List[float], percentile: float) -> float:
        """Вычисляет перцентиль."""
        if not values:
            return 0
        
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile)
        return sorted_values[min(index, len(sorted_values) - 1)]
    
    def collect_system_metrics(self):
        """Собирает системные метрики."""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent()
            self.record_metric("system_cpu_percent", cpu_percent, unit="percent")
            
            # Memory
            memory = psutil.virtual_memory()
            self.record_metric("system_memory_percent", memory.percent, unit="percent")
            self.record_metric("system_memory_available_mb", memory.available / 1024 / 1024, unit="megabytes")
            
            # Disk
            disk = psutil.disk_usage('/')
            self.record_metric("system_disk_percent", disk.percent, unit="percent")
            self.record_metric("system_disk_free_gb", disk.free / 1024 / 1024 / 1024, unit="gigabytes")
            
            # Network (if available)
            try:
                net = psutil.net_io_counters()
                self.record_metric("system_bytes_sent", net.bytes_sent, unit="bytes")
                self.record_metric("system_bytes_received", net.bytes_recv, unit="bytes")
            except:
                pass  # Network metrics not available
                
        except Exception as e:
            logger.warning(f"Failed to collect system metrics: {e}")
    
    def get_system_health(self) -> Dict[str, Any]:
        """Возвращает оценку здоровья системы."""
        try:
            cpu = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Определяем статус на основе метрик
            status = "healthy"
            issues = []
            
            if cpu > 80:
                status = "warning"
                issues.append(f"Высокая загрузка CPU: {cpu:.1f}%")
            
            if memory.percent > 85:
                status = "critical" if status != "critical" else status
                issues.append(f"Высокое использование памяти: {memory.percent:.1f}%")
            
            if disk.percent > 90:
                status = "critical"
                issues.append(f"Мало свободного места: {disk.percent:.1f}%")
            
            return {
                "status": status,
                "issues": issues,
                "metrics": {
                    "cpu_percent": cpu,
                    "memory_percent": memory.percent,
                    "memory_available_mb": memory.available / 1024 / 1024,
                    "disk_percent": disk.percent,
                    "disk_free_gb": disk.free / 1024 / 1024 / 1024
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_all_metrics_summary(self) -> Dict[str, Any]:
        """Возвращает сводку всех метрик."""
        # Группируем метрики по именам
        metric_groups = defaultdict(list)
        cutoff_time = datetime.now() - timedelta(hours=1)  # Последний час
        
        for metric in self.metrics:
            if metric.timestamp > cutoff_time:
                metric_groups[metric.name].append(metric)
        
        summary = {}
        for name, metrics_list in metric_groups.items():
            values = [m.value for m in metrics_list]
            if values:
                summary[name] = {
                    "count": len(values),
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "last": values[-1],
                    "unit": metrics_list[-1].unit
                }
        
        return summary
    
    def cleanup_old_metrics(self):
        """Очищает старые метрики."""
        cutoff_time = datetime.now() - timedelta(hours=self.retention_hours)
        
        # Очищаем старые метрики
        while self.metrics and self.metrics[0].timestamp < cutoff_time:
            self.metrics.popleft()
        
        # Очищаем старые операции (на всякий случай)
        current_time = datetime.now()
        stale_operations = [
            op_id for op_id, trace in self.operation_traces.items()
            if current_time - trace.start_time > timedelta(hours=1)
        ]
        
        for op_id in stale_operations:
            logger.warning(f"Cleaning up stale operation: {op_id}")
            self.finish_operation(op_id, success=False, error="Operation timed out")


class BusinessMetricsTracker:
    """Отслеживает бизнес-метрики системы."""
    
    def __init__(self):
        self.metrics = defaultdict(int)
        self.daily_metrics = defaultdict(lambda: defaultdict(int))
    
    def track_user_interaction(self, interaction_type: str, user_id: str = None):
        """Отслеживает взаимодействие пользователя."""
        today = datetime.now().date()
        
        self.metrics[f"interactions_{interaction_type}"] += 1
        self.daily_metrics[today][f"interactions_{interaction_type}"] += 1
        
        if user_id:
            self.daily_metrics[today][f"unique_users"] = len(
                set(self.daily_metrics[today].get("user_ids", []) + [user_id])
            )
    
    def track_agent_usage(self, agent_type: str, success: bool = True):
        """Отслеживает использование агентов."""
        today = datetime.now().date()
        
        self.metrics[f"agent_{agent_type}_total"] += 1
        self.daily_metrics[today][f"agent_{agent_type}_total"] += 1
        
        if success:
            self.metrics[f"agent_{agent_type}_success"] += 1
            self.daily_metrics[today][f"agent_{agent_type}_success"] += 1
        else:
            self.metrics[f"agent_{agent_type}_errors"] += 1
            self.daily_metrics[today][f"agent_{agent_type}_errors"] += 1
    
    def track_notion_operation(self, operation: str, success: bool = True):
        """Отслеживает операции с Notion."""
        today = datetime.now().date()
        
        self.metrics[f"notion_{operation}"] += 1
        self.daily_metrics[today][f"notion_{operation}"] += 1
        
        if not success:
            self.metrics[f"notion_{operation}_errors"] += 1
            self.daily_metrics[today][f"notion_{operation}_errors"] += 1
    
    def get_daily_summary(self, date: datetime.date = None) -> Dict[str, Any]:
        """Получает сводку за день."""
        target_date = date or datetime.now().date()
        day_metrics = self.daily_metrics.get(target_date, {})
        
        return {
            "date": target_date.isoformat(),
            "metrics": dict(day_metrics)
        }
    
    def get_business_kpis(self) -> Dict[str, Any]:
        """Возвращает ключевые бизнес-показатели."""
        total_interactions = sum(
            count for name, count in self.metrics.items()
            if name.startswith("interactions_")
        )
        
        total_agent_calls = sum(
            count for name, count in self.metrics.items() 
            if "agent_" in name and "_total" in name
        )
        
        total_agent_errors = sum(
            count for name, count in self.metrics.items()
            if "agent_" in name and "_errors" in name
        )
        
        agent_success_rate = 1.0
        if total_agent_calls > 0:
            agent_success_rate = 1.0 - (total_agent_errors / total_agent_calls)
        
        return {
            "total_user_interactions": total_interactions,
            "total_agent_calls": total_agent_calls,
            "agent_success_rate": agent_success_rate,
            "notion_operations": self.metrics.get("notion_create_page", 0) + self.metrics.get("notion_update_page", 0),
            "uptime_info": self._get_uptime_info()
        }
    
    def _get_uptime_info(self) -> Dict[str, Any]:
        """Получает информацию о времени работы."""
        try:
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            
            return {
                "system_uptime_hours": uptime.total_seconds() / 3600,
                "boot_time": boot_time.isoformat()
            }
        except:
            return {"uptime_info": "unavailable"}


class PerformanceMonitor:
    """Основной класс мониторинга производительности."""
    
    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.business_tracker = BusinessMetricsTracker()
        self.active_operations = {}
        self.performance_alerts = []
        
        # Пороговые значения для алертов
        self.thresholds = {
            "response_time_ms": 5000,      # 5 секунд
            "error_rate": 0.05,            # 5% ошибок
            "cpu_percent": 80,             # 80% CPU
            "memory_percent": 85,          # 85% памяти
        }
    
    def start_operation_trace(self, operation_name: str) -> str:
        """Начинает трассировку операции."""
        return self.metrics_collector.start_operation(operation_name)
    
    def finish_operation_trace(
        self,
        operation_id: str,
        success: bool = True,
        error: str = None,
        metadata: Dict[str, Any] = None
    ):
        """Завершает трассировку операции."""
        self.metrics_collector.finish_operation(
            operation_id, success, error, metadata
        )
    
    def record_response_time(self, endpoint: str, duration_ms: float):
        """Записывает время ответа endpoint."""
        self.metrics_collector.record_metric(
            "http_request_duration_ms",
            duration_ms,
            labels={"endpoint": endpoint},
            unit="milliseconds"
        )
        
        # Проверяем превышение порога
        if duration_ms > self.thresholds["response_time_ms"]:
            self._trigger_performance_alert(
                "slow_response",
                f"Медленный ответ {endpoint}: {duration_ms:.0f}мс",
                {"endpoint": endpoint, "duration_ms": duration_ms}
            )
    
    def record_ollama_request(self, model: str, duration_ms: float, tokens: int = None):
        """Записывает запрос к Ollama."""
        self.metrics_collector.record_metric(
            "ollama_request_duration_ms",
            duration_ms,
            labels={"model": model},
            unit="milliseconds"
        )
        
        if tokens:
            self.metrics_collector.record_metric(
                "ollama_tokens_processed",
                tokens,
                labels={"model": model},
                unit="tokens"
            )
    
    def record_database_query(self, query_type: str, duration_ms: float):
        """Записывает запрос к базе данных."""
        self.metrics_collector.record_metric(
            "database_query_duration_ms", 
            duration_ms,
            labels={"query_type": query_type},
            unit="milliseconds"
        )
    
    def collect_system_metrics(self):
        """Собирает системные метрики."""
        self.metrics_collector.collect_system_metrics()
        
        # Проверяем системные пороги
        system_health = self.metrics_collector.get_system_health()
        if system_health["status"] in ["warning", "critical"]:
            self._trigger_performance_alert(
                f"system_{system_health['status']}",
                f"Системные проблемы: {', '.join(system_health.get('issues', []))}",
                system_health["metrics"]
            )
    
    def _trigger_performance_alert(
        self,
        alert_type: str,
        message: str,
        context: Dict[str, Any] = None
    ):
        """Создает алерт производительности."""
        alert = {
            "type": alert_type,
            "message": message,
            "timestamp": datetime.now(),
            "context": context or {}
        }
        
        self.performance_alerts.append(alert)
        
        # Ограничиваем количество алертов
        if len(self.performance_alerts) > 100:
            self.performance_alerts.pop(0)
        
        logger.warning(f"Performance alert: {alert_type} - {message}")
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Создает отчет производительности."""
        # Основные операции для мониторинга
        key_operations = [
            "telegram_message_processing",
            "ollama_generate_response", 
            "notion_create_page",
            "database_query",
            "rag_search"
        ]
        
        operation_stats = {}
        for op in key_operations:
            operation_stats[op] = self.metrics_collector.get_operation_stats(op)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "system_health": self.metrics_collector.get_system_health(),
            "business_kpis": self.business_tracker.get_business_kpis(),
            "operation_performance": operation_stats,
            "recent_alerts": self.performance_alerts[-10:],  # Последние 10 алертов
            "metrics_summary": self.metrics_collector.get_all_metrics_summary()
        }
    
    def start_background_collection(self):
        """Запускает фоновый сбор системных метрик."""
        async def collect_loop():
            while True:
                try:
                    self.collect_system_metrics()
                    self.metrics_collector.cleanup_old_metrics()
                    await asyncio.sleep(30)  # Каждые 30 секунд
                except Exception as e:
                    logger.error(f"Error in metrics collection loop: {e}")
                    await asyncio.sleep(60)  # При ошибке ждем дольше
        
        asyncio.create_task(collect_loop())
        logger.info("Performance monitoring background collection started")


# Глобальный экземпляр
_performance_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """Получает глобальный экземпляр мониторинга производительности."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


def track_operation(operation_name: str):
    """Декоратор для автоматического трекинга операций."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            monitor = get_performance_monitor()
            op_id = monitor.start_operation_trace(operation_name)
            
            try:
                result = await func(*args, **kwargs)
                monitor.finish_operation_trace(op_id, success=True)
                return result
            except Exception as e:
                monitor.finish_operation_trace(op_id, success=False, error=str(e))
                raise
        
        return wrapper
    return decorator