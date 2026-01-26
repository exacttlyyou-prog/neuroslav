"""
Unit тесты для системы кеширования.
"""
import pytest
import asyncio
from datetime import datetime, timedelta

from app.core.cache import InMemoryCache, OllamaCacheService, CacheEntry


class TestCacheEntry:
    """Тесты для CacheEntry."""
    
    def test_cache_entry_creation(self):
        """Тест создания записи кеша."""
        value = "test_value"
        entry = CacheEntry(value, ttl_seconds=300)
        
        assert entry.value == value
        assert entry.hit_count == 0
        assert isinstance(entry.created_at, datetime)
        assert isinstance(entry.expires_at, datetime)
        assert entry.expires_at > entry.created_at
    
    def test_cache_entry_expiration(self):
        """Тест истечения записи кеша."""
        entry = CacheEntry("value", ttl_seconds=0)  # Истекает немедленно
        
        # Небольшая задержка
        import time
        time.sleep(0.001)
        
        assert entry.is_expired()
    
    def test_cache_entry_access(self):
        """Тест доступа к записи кеша."""
        entry = CacheEntry("value", ttl_seconds=300)
        
        assert entry.hit_count == 0
        result = entry.access()
        
        assert result == "value"
        assert entry.hit_count == 1
        assert entry.last_accessed > entry.created_at


class TestInMemoryCache:
    """Тесты для InMemoryCache."""
    
    def test_cache_get_miss(self):
        """Тест cache miss."""
        cache = InMemoryCache()
        result = cache.get("nonexistent_key")
        
        assert result is None
        stats = cache.get_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 0
    
    def test_cache_set_and_get_hit(self):
        """Тест set и cache hit."""
        cache = InMemoryCache()
        key = "test_key"
        value = "test_value"
        
        cache.set(key, value, ttl_seconds=300)
        result = cache.get(key)
        
        assert result == value
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 0
        assert stats["cache_size"] == 1
    
    def test_cache_ttl_expiration(self):
        """Тест истечения TTL."""
        cache = InMemoryCache()
        key = "test_key"
        value = "test_value"
        
        # Устанавливаем с TTL 0 (истекает немедленно)
        cache.set(key, value, ttl_seconds=0)
        
        # Небольшая задержка
        import time
        time.sleep(0.001)
        
        result = cache.get(key)
        assert result is None
        
        stats = cache.get_stats()
        assert stats["misses"] == 1
    
    def test_cache_eviction(self):
        """Тест вытеснения при превышении размера."""
        cache = InMemoryCache(max_size=2)
        
        # Добавляем 3 элемента
        cache.set("key1", "value1")
        cache.set("key2", "value2") 
        cache.set("key3", "value3")  # Должен вытеснить самый старый
        
        stats = cache.get_stats()
        assert stats["cache_size"] == 2
        assert stats["evictions"] >= 1
    
    def test_cache_clear(self):
        """Тест очистки кеша."""
        cache = InMemoryCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        cache.clear()
        
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        stats = cache.get_stats()
        assert stats["cache_size"] == 0
    
    def test_cache_hit_rate(self):
        """Тест расчета hit rate."""
        cache = InMemoryCache()
        cache.set("key", "value")
        
        # 1 hit, 1 miss
        cache.get("key")      # hit
        cache.get("missing")  # miss
        
        stats = cache.get_stats()
        assert stats["hit_rate"] == 0.5
    
    def test_key_generation(self):
        """Тест генерации ключей."""
        cache = InMemoryCache()
        
        key1 = cache._generate_key("prefix", "arg1", kwarg="value")
        key2 = cache._generate_key("prefix", "arg1", kwarg="value")
        key3 = cache._generate_key("prefix", "arg2", kwarg="value")
        
        # Одинаковые параметры должны давать одинаковые ключи
        assert key1 == key2
        
        # Разные параметры должны давать разные ключи
        assert key1 != key3


class TestOllamaCacheService:
    """Тесты для OllamaCacheService."""
    
    def test_cache_persona_response(self):
        """Тест кеширования persona response."""
        cache = InMemoryCache()
        ollama_cache = OllamaCacheService(cache)
        
        user_input = "тестовый вопрос"
        context = "тестовый контекст"
        response = "тестовый ответ"
        
        # Проверяем что кеша нет
        cached = ollama_cache.get_cached_response(
            "persona_response",
            user_input=user_input,
            context=context
        )
        assert cached is None
        
        # Кешируем ответ
        ollama_cache.cache_response(
            "persona_response",
            response,
            user_input=user_input, 
            context=context
        )
        
        # Проверяем что ответ закеширован
        cached = ollama_cache.get_cached_response(
            "persona_response",
            user_input=user_input,
            context=context
        )
        assert cached == response
    
    def test_different_ttl_for_request_types(self):
        """Тест разных TTL для разных типов запросов."""
        cache = InMemoryCache()
        ollama_cache = OllamaCacheService(cache)
        
        # Проверяем что разные типы имеют разные TTL
        assert ollama_cache.ttl_config["persona_response"] == 60
        assert ollama_cache.ttl_config["classification"] == 300
        assert ollama_cache.ttl_config["analysis"] == 600
        assert ollama_cache.ttl_config["summarization"] == 900
    
    def test_cache_key_uniqueness(self):
        """Тест уникальности ключей для разных параметров."""
        cache = InMemoryCache()
        ollama_cache = OllamaCacheService(cache)
        
        # Кешируем разные запросы
        ollama_cache.cache_response("persona_response", "ответ1", user_input="вопрос1")
        ollama_cache.cache_response("persona_response", "ответ2", user_input="вопрос2") 
        ollama_cache.cache_response("classification", "ответ3", user_input="вопрос1")
        
        # Проверяем что они не перезаписывают друг друга
        assert ollama_cache.get_cached_response("persona_response", user_input="вопрос1") == "ответ1"
        assert ollama_cache.get_cached_response("persona_response", user_input="вопрос2") == "ответ2"
        assert ollama_cache.get_cached_response("classification", user_input="вопрос1") == "ответ3"


@pytest.mark.asyncio
class TestCacheIntegration:
    """Интеграционные тесты кеша."""
    
    async def test_concurrent_access(self):
        """Тест параллельного доступа к кешу."""
        cache = InMemoryCache()
        
        async def set_and_get(key: str, value: str):
            cache.set(key, value)
            return cache.get(key)
        
        # Запускаем несколько параллельных операций
        tasks = [
            set_and_get(f"key{i}", f"value{i}")
            for i in range(10)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Проверяем что все операции прошли успешно
        for i, result in enumerate(results):
            assert result == f"value{i}"
    
    async def test_cache_performance(self):
        """Тест производительности кеша."""
        cache = InMemoryCache(max_size=1000)
        
        # Засекаем время записи
        start_time = datetime.now()
        for i in range(100):
            cache.set(f"key{i}", f"value{i}")
        write_time = (datetime.now() - start_time).total_seconds()
        
        # Засекаем время чтения
        start_time = datetime.now()
        for i in range(100):
            cache.get(f"key{i}")
        read_time = (datetime.now() - start_time).total_seconds()
        
        # Проверяем что операции быстрые (< 1 секунды для 100 операций)
        assert write_time < 1.0
        assert read_time < 1.0
        
        stats = cache.get_stats()
        assert stats["hit_rate"] == 1.0  # Все запросы должны быть hits