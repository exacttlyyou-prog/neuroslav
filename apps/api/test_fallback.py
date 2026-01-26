#!/usr/bin/env python3
"""
Тестируем fallback систему OllamaService.
"""
import asyncio
import sys
from pathlib import Path

# Добавляем пути
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

api_root = project_root / "apps" / "api"
sys.path.append(str(api_root))

# Исправляем путь к БД
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import os
database_url = os.getenv("DATABASE_URL", "sqlite:///./data/digital_twin.db")
if "sqlite:///" in database_url and not database_url.startswith("sqlite:////"):
    relative_path = database_url.split("sqlite:///")[1]
    if relative_path.startswith("./"):
        relative_path = relative_path[2:]
    db_path = api_root / relative_path
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"


async def test_fallback():
    """Тест fallback-ов."""
    try:
        from apps.api.app.services.ollama_service import OllamaService
        
        print("🧪 Тестируем OllamaService fallback...")
        
        ollama = OllamaService()
        
        # Тестируем работу с простым вопросом
        print("\n1️⃣ Тест: простой вопрос 'работаешь?'")
        try:
            response = await ollama.generate_persona_response("работаешь?", "")
            print(f"✅ Ответ: {response}")
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        
        # Тестируем fallback систему напрямую
        print("\n2️⃣ Тест: fallback для task")
        fallback = ollama._get_fallback_response("создай задачу", "task context")
        print(f"✅ Fallback: {fallback}")
        
        # Тестируем через DefaultAgent
        print("\n3️⃣ Тест: DefaultAgent")
        from apps.api.app.services.agents.default_agent import DefaultAgent
        agent = DefaultAgent()
        
        # Создаем фиктивную классификацию
        from apps.api.app.models.schemas import IntentClassification
        classification = IntentClassification(
            agent_type="default",
            confidence=0.8,
            extracted_data={},
            reasoning="Тестовая классификация"
        )
        
        result = await agent._process_with_context("работаешь?", classification, [])
        print(f"✅ DefaultAgent ответ: {result['response']}")
        
    except Exception as e:
        print(f"❌ Критическая ошибка теста: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_fallback())