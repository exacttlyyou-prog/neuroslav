import asyncio
import os
import sys
from pathlib import Path
import httpx
from dotenv import load_dotenv

# Загружаем .env
env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(env_path)

async def check_token_deep():
    token = os.getenv("NOTION_TOKEN")
    
    print(f"\n🔍 Анализ токена:")
    print(f"Original from env: {token}")
    print(f"Repr (hidden chars): {repr(token)}")
    
    if not token:
        print("❌ Empty token")
        return

    # Проверка на пробелы
    if token.strip() != token:
        print("⚠️  ВНИМАНИЕ: Токен содержит пробелы в начале или конце! Это причина ошибки.")
    
    clean_token = token.strip()
    
    # Варианты заголовков для проверки
    variants = [
        ("Bearer", {"Authorization": f"Bearer {clean_token}"}),
        ("Basic", {"Authorization": f"Basic {clean_token}"}),
        ("No Prefix", {"Authorization": clean_token}),
    ]
    
    url = "https://api.notion.com/v1/users/me"
    
    async with httpx.AsyncClient() as client:
        for name, headers in variants:
            headers["Notion-Version"] = "2022-06-28"
            headers["Content-Type"] = "application/json"
            
            print(f"\n📡 Попытка: {name}")
            try:
                response = await client.get(url, headers=headers)
                print(f"Status: {response.status_code}")
                if response.status_code == 200:
                    print(f"✅ УСПЕХ! Сработал вариант: {name}")
                    return
                else:
                    print(f"Ответ: {response.json().get('message')}")
            except Exception as e:
                print(f"Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(check_token_deep())
