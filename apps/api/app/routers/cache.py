"""
API endpoints для управления кешем и мониторинга производительности.
"""
from fastapi import APIRouter
from typing import Dict, Any, List
from loguru import logger

from app.core.cache import get_cache, clear_all_caches

router = APIRouter()


@router.get("/stats")
async def get_cache_stats() -> Dict[str, Any]:
    """Получить статистику кеша."""
    try:
        cache = get_cache()
        stats = cache.get_stats()
        
        return {
            "status": "success",
            "cache_stats": stats,
            "recommendations": _generate_recommendations(stats)
        }
    except Exception as e:
        logger.error(f"Ошибка получения статистики кеша: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.post("/clear")
async def clear_cache() -> Dict[str, str]:
    """Очистить весь кеш."""
    try:
        clear_all_caches()
        logger.info("Кеш очищен через API endpoint")
        
        return {
            "status": "success",
            "message": "Кеш успешно очищен"
        }
    except Exception as e:
        logger.error(f"Ошибка очистки кеша: {e}")
        return {
            "status": "error",
            "message": f"Ошибка очистки кеша: {str(e)}"
        }


@router.get("/health")
async def cache_health() -> Dict[str, Any]:
    """Проверка здоровья системы кеширования."""
    try:
        cache = get_cache()
        stats = cache.get_stats()
        
        # Определяем состояние здоровья
        health_status = "healthy"
        issues = []
        
        # Проверка hit rate
        if stats["hit_rate"] < 0.3 and stats["total_requests"] > 10:
            health_status = "warning"
            issues.append("Низкий hit rate кеша (< 30%)")
        
        # Проверка заполненности кеша
        if stats["cache_size"] >= stats["max_size"] * 0.9:
            health_status = "warning"
            issues.append("Кеш почти полон (>90%)")
        
        # Проверка частых evictions
        if stats["evictions"] > stats["hits"] and stats["total_requests"] > 20:
            health_status = "critical"
            issues.append("Слишком много evictions - возможно нужно увеличить размер кеша")
        
        return {
            "status": health_status,
            "issues": issues,
            "stats": stats,
            "uptime_info": "Кеш работает в памяти",
            "recommendations": _generate_recommendations(stats)
        }
        
    except Exception as e:
        logger.error(f"Ошибка проверки здоровья кеша: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


def _generate_recommendations(stats: Dict[str, Any]) -> List[str]:
    """Генерирует рекомендации на основе статистики кеша."""
    recommendations = []
    
    # Рекомендации по hit rate
    if stats["hit_rate"] < 0.3 and stats["total_requests"] > 10:
        recommendations.append("Низкий hit rate. Рассмотрите увеличение TTL для часто используемых данных")
    elif stats["hit_rate"] > 0.8:
        recommendations.append("Отличный hit rate! Кеш работает эффективно")
    
    # Рекомендации по размеру
    if stats["cache_size"] >= stats["max_size"] * 0.8:
        recommendations.append("Кеш заполнен на >80%. Рассмотрите увеличение max_size")
    
    # Рекомендации по evictions
    if stats["evictions"] > stats["hits"] / 2:
        recommendations.append("Много evictions. Возможно стоит увеличить размер кеша или уменьшить TTL")
    
    if not recommendations:
        recommendations.append("Кеш работает оптимально")
    
    return recommendations