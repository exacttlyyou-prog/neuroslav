"""
Система кеширования для оптимизации производительности.
Включает в себя кеширование Ollama запросов и контекста.
"""
import hashlib
import json
import time
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
from loguru import logger


class CacheEntry:
    """Запись в кеше с метаданными."""
    
    def __init__(self, value: Any, ttl_seconds: int = 300):
        self.value = value
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)
        self.hit_count = 0
        self.last_accessed = self.created_at
    
    def is_expired(self) -> bool:
        """Проверяет, истекла ли запись."""
        return datetime.now() > self.expires_at
    
    def access(self) -> Any:
        """Получает значение и обновляет статистику."""
        self.hit_count += 1
        self.last_accessed = datetime.now()
        return self.value


class InMemoryCache:
    """Простой кеш в памяти с TTL и статистикой."""
    
    def __init__(self, max_size: int = 1000):
        self._cache: Dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "total_requests": 0
        }
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Генерирует ключ кеша на основе аргументов."""
        # Создаем детерминированную строку из аргументов
        key_data = {
            "args": args,
            "kwargs": sorted(kwargs.items())  # Сортируем для консистентности
        }
        key_string = f"{prefix}:{json.dumps(key_data, sort_keys=True)}"
        
        # Хешируем для получения фиксированной длины ключа
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Получает значение из кеша."""
        self._stats["total_requests"] += 1
        
        if key in self._cache:
            entry = self._cache[key]
            
            if entry.is_expired():
                # Запись истекла, удаляем
                del self._cache[key]
                self._stats["misses"] += 1
                return None
            
            self._stats["hits"] += 1
            return entry.access()
        
        self._stats["misses"] += 1
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Сохраняет значение в кеш."""
        # Проверяем размер кеша
        if len(self._cache) >= self._max_size:
            self._evict_oldest()
        
        self._cache[key] = CacheEntry(value, ttl_seconds)
    
    def _evict_oldest(self):
        """Удаляет самую старую запись."""
        if not self._cache:
            return
        
        # Находим запись с самым старым last_accessed
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed
        )
        
        del self._cache[oldest_key]
        self._stats["evictions"] += 1
    
    def clear(self):
        """Очищает весь кеш."""
        self._cache.clear()
        logger.info("Кеш очищен")
    
    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику кеша."""
        hit_rate = 0
        if self._stats["total_requests"] > 0:
            hit_rate = self._stats["hits"] / self._stats["total_requests"]
        
        return {
            **self._stats,
            "hit_rate": hit_rate,
            "cache_size": len(self._cache),
            "max_size": self._max_size
        }


class OllamaCacheService:
    """Специализированный кеш для Ollama запросов."""
    
    def __init__(self, cache: InMemoryCache):
        self.cache = cache
        
        # Разные TTL для разных типов запросов
        self.ttl_config = {
            "persona_response": 60,  # 1 минута для персона-ответов
            "classification": 300,   # 5 минут для классификации
            "analysis": 600,        # 10 минут для анализа
            "summarization": 900    # 15 минут для суммаризации
        }
    
    def get_cached_response(
        self, 
        request_type: str, 
        user_input: str = "", 
        context: str = "",
        **kwargs
    ) -> Optional[str]:
        """Получает кешированный ответ Ollama."""
        key = self.cache._generate_key(
            f"ollama:{request_type}",
            user_input=user_input,
            context=context,
            **kwargs
        )
        
        cached = self.cache.get(key)
        if cached:
            logger.debug(f"Кеш попадание для Ollama {request_type}: {user_input[:50]}...")
        
        return cached
    
    def cache_response(
        self,
        request_type: str,
        response: str,
        user_input: str = "",
        context: str = "",
        **kwargs
    ):
        """Кеширует ответ Ollama."""
        key = self.cache._generate_key(
            f"ollama:{request_type}",
            user_input=user_input,
            context=context,
            **kwargs
        )
        
        ttl = self.ttl_config.get(request_type, 300)
        self.cache.set(key, response, ttl)
        
        logger.debug(f"Кешируем Ollama {request_type} на {ttl}с: {user_input[:50]}...")


# Глобальный экземпляр кеша
_cache_instance: Optional[InMemoryCache] = None
_ollama_cache_instance: Optional[OllamaCacheService] = None


def get_cache() -> InMemoryCache:
    """Получает глобальный экземпляр кеша."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = InMemoryCache(max_size=1000)
        logger.info("Инициализирован кеш в памяти")
    return _cache_instance


def get_ollama_cache() -> OllamaCacheService:
    """Получает специализированный кеш для Ollama."""
    global _ollama_cache_instance
    if _ollama_cache_instance is None:
        _ollama_cache_instance = OllamaCacheService(get_cache())
        logger.info("Инициализирован Ollama кеш")
    return _ollama_cache_instance


def clear_all_caches():
    """Очищает все кеши."""
    cache = get_cache()
    cache.clear()
    logger.info("Все кеши очищены")