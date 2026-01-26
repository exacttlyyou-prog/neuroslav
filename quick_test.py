#!/usr/bin/env python3
"""
Быстрый тест fallback без полной инициализации.
"""
import sys
from pathlib import Path

# Добавляем пути
project_root = Path(__file__).parent
sys.path.append(str(project_root))

api_root = project_root / "apps" / "api"
sys.path.append(str(api_root))

try:
    from apps.api.app.services.ollama_service import OllamaService
    
    print("🧪 Быстрый тест fallback системы...")
    
    # Создаем OllamaService без инициализации RAG
    class MockContextLoader:
        pass
    
    # Пробуем создать OllamaService и протестировать fallback
    try:
        ollama = OllamaService(context_loader=MockContextLoader())
        
        # Тестируем fallback напрямую
        fallback_response = ollama._get_fallback_response("работаешь?", "")
        print(f"✅ Fallback работает: {fallback_response}")
        
        # Проверяем что это НЕ старое сообщение
        if "Сделано. Но ответ от AI пустой" in fallback_response:
            print("❌ ОШИБКА: Все еще используется старое сообщение!")
        else:
            print("✅ Новый fallback работает правильно!")
            
    except Exception as e:
        print(f"❌ Ошибка создания OllamaService: {e}")
    
    print("\n📝 Заключение:")
    print("Если видите '✅ Новый fallback работает правильно!' - изменения в коде есть.")
    print("Если бот все еще показывает старые сообщения - нужно перезапустить поллинг-скрипт!")
    
except Exception as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Возможно, нужно настроить переменные окружения.")