"""
API endpoints для мониторинга производительности и системы.
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any
from datetime import datetime, date
from loguru import logger

from app.core.monitoring import get_performance_monitor
from app.core.errors import get_error_tracker  
from app.core.cache import get_cache

router = APIRouter()


@router.get("/health")
async def system_health() -> Dict[str, Any]:
    """Проверка здоровья системы."""
    try:
        monitor = get_performance_monitor()
        system_health = monitor.metrics_collector.get_system_health()
        
        # Добавляем информацию о сервисах
        services_status = {}
        
        # Проверяем основные сервисы
        try:
            from app.services.ollama_service import OllamaService
            ollama = OllamaService()
            services_status["ollama"] = "healthy"  # Базовая проверка инициализации
        except Exception as e:
            services_status["ollama"] = f"error: {str(e)}"
        
        try:
            from app.services.notion_service import NotionService  
            notion = NotionService()
            services_status["notion"] = "healthy"
        except Exception as e:
            services_status["notion"] = f"error: {str(e)}"
        
        # Проверяем кеш
        cache = get_cache()
        cache_stats = cache.get_stats()
        services_status["cache"] = "healthy" if cache_stats["cache_size"] >= 0 else "error"
        
        return {
            "status": system_health["status"],
            "timestamp": datetime.now().isoformat(),
            "system_metrics": system_health["metrics"],
            "services": services_status,
            "issues": system_health.get("issues", [])
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/metrics")
async def performance_metrics() -> Dict[str, Any]:
    """Получить метрики производительности."""
    try:
        monitor = get_performance_monitor()
        report = monitor.get_performance_report()
        
        # Добавляем метрики ошибок
        error_tracker = get_error_tracker()
        error_stats = error_tracker.get_error_statistics()
        
        # Добавляем метрики кеша
        cache = get_cache()
        cache_stats = cache.get_stats()
        
        return {
            "performance": report,
            "errors": error_stats,
            "cache": cache_stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/metrics/business")
async def business_metrics() -> Dict[str, Any]:
    """Получить бизнес-метрики."""
    try:
        monitor = get_performance_monitor()
        business_kpis = monitor.business_tracker.get_business_kpis()
        
        # Дневная сводка
        today_summary = monitor.business_tracker.get_daily_summary()
        
        return {
            "kpis": business_kpis,
            "daily": today_summary,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get business metrics: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/metrics/operations/{operation_name}")
async def operation_metrics(operation_name: str) -> Dict[str, Any]:
    """Получить метрики конкретной операции."""
    try:
        monitor = get_performance_monitor()
        stats = monitor.metrics_collector.get_operation_stats(operation_name)
        
        return {
            "operation_stats": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get operation metrics: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/alerts")
async def recent_alerts() -> Dict[str, Any]:
    """Получить последние алерты производительности."""
    try:
        monitor = get_performance_monitor()
        
        # Форматируем алерты для JSON
        formatted_alerts = []
        for alert in monitor.performance_alerts[-50:]:  # Последние 50
            formatted_alert = {
                "type": alert["type"],
                "message": alert["message"],
                "timestamp": alert["timestamp"].isoformat(),
                "context": alert["context"]
            }
            formatted_alerts.append(formatted_alert)
        
        return {
            "alerts": formatted_alerts,
            "count": len(formatted_alerts)
        }
        
    except Exception as e:
        logger.error(f"Failed to get alerts: {e}")
        return {
            "error": str(e),
            "alerts": []
        }


@router.post("/metrics/track")
async def track_custom_metric(
    metric_name: str,
    value: float,
    unit: str = "count",
    labels: Dict[str, str] = None
) -> Dict[str, str]:
    """Записать кастомную метрику."""
    try:
        monitor = get_performance_monitor()
        monitor.metrics_collector.record_metric(
            name=metric_name,
            value=value,
            unit=unit,
            labels=labels or {}
        )
        
        return {
            "status": "recorded",
            "metric": metric_name,
            "value": str(value)
        }
        
    except Exception as e:
        logger.error(f"Failed to track metric: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/debug/system")
async def system_debug_info() -> Dict[str, Any]:
    """Получить отладочную информацию о системе."""
    try:
        import psutil
        import sys
        import os
        
        process = psutil.Process()
        
        debug_info = {
            "python_version": sys.version,
            "platform": sys.platform,
            "process_info": {
                "pid": process.pid,
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "cpu_percent": process.cpu_percent(),
                "num_threads": process.num_threads(),
                "create_time": datetime.fromtimestamp(process.create_time()).isoformat(),
                "status": process.status()
            },
            "environment": {
                "working_directory": os.getcwd(),
                "environment_vars": len(os.environ),
                "user": os.getenv("USER", "unknown")
            }
        }
        
        # Добавляем информацию о модулях
        monitor = get_performance_monitor()
        error_tracker = get_error_tracker()
        cache = get_cache()
        
        debug_info["internal_state"] = {
            "active_operations": len(monitor.metrics_collector.operation_traces),
            "total_metrics": len(monitor.metrics_collector.metrics),
            "performance_alerts": len(monitor.performance_alerts),
            "error_counts": len(error_tracker.error_counts),
            "cache_size": cache.get_stats()["cache_size"]
        }
        
        return debug_info
        
    except Exception as e:
        logger.error(f"Failed to get debug info: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/prometheus")
async def prometheus_metrics() -> str:
    """Метрики в формате Prometheus."""
    try:
        monitor = get_performance_monitor()
        cache = get_cache()
        error_tracker = get_error_tracker()
        
        lines = []
        
        # Системные метрики
        system_health = monitor.metrics_collector.get_system_health()
        if "metrics" in system_health:
            metrics = system_health["metrics"]
            lines.append(f"# HELP system_cpu_percent CPU usage percentage")
            lines.append(f"# TYPE system_cpu_percent gauge") 
            lines.append(f"system_cpu_percent {metrics.get('cpu_percent', 0)}")
            
            lines.append(f"# HELP system_memory_percent Memory usage percentage")
            lines.append(f"# TYPE system_memory_percent gauge")
            lines.append(f"system_memory_percent {metrics.get('memory_percent', 0)}")
        
        # Кеш метрики
        cache_stats = cache.get_stats()
        lines.append(f"# HELP cache_hit_rate Cache hit rate")
        lines.append(f"# TYPE cache_hit_rate gauge")
        lines.append(f"cache_hit_rate {cache_stats.get('hit_rate', 0)}")
        
        lines.append(f"# HELP cache_size Current cache size")  
        lines.append(f"# TYPE cache_size gauge")
        lines.append(f"cache_size {cache_stats.get('cache_size', 0)}")
        
        # Ошибки
        error_stats = error_tracker.get_error_statistics()
        lines.append(f"# HELP total_errors Total number of errors")
        lines.append(f"# TYPE total_errors counter")
        lines.append(f"total_errors {error_stats.get('total_errors', 0)}")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Failed to generate Prometheus metrics: {e}")
        return f"# Error generating metrics: {str(e)}"