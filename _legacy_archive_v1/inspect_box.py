import asyncio
import os
import json
from dotenv import load_dotenv
from notion_client import AsyncClient

load_dotenv()

# ID проблемного блока из твоих логов
TARGET_BLOCK_ID = "2edfa7fd-6371-80f5-8343-db4c001f1916"

async def open_black_box():
    token = os.getenv("NOTION_TOKEN")
    if not token:
        print("❌ Нет токена")
        return

    client = AsyncClient(auth=token)
    print(f"📦 Вскрываем блок {TARGET_BLOCK_ID}...")

    try:
        # Пытаемся получить детей
        response = await client.blocks.children.list(block_id=TARGET_BLOCK_ID)
        children = response["results"]

        if not children:
            print("📭 Блок пуст (API вернул 0 детей).")
            print("ВЫВОД: Это закрытый блок (например, Notion AI Transcription), API его не отдает.")
            print("РЕШЕНИЕ: Скопировать текст руками в обычный блок.")
            return

        print(f"✅ Найдено {len(children)} вложенных блоков!")
        print("Вот их типы (чтобы мы научили бота их читать):")
        
        for child in children:
            c_type = child["type"]
            # Пытаемся найти текст в стандартных местах
            text = "???"
            if "rich_text" in child.get(c_type, {}):
                text_obj = child[c_type]["rich_text"]
                text = "".join([t["plain_text"] for t in text_obj])
            
            print(f"🔹 Тип: {c_type:<20} | Текст: {text[:40]}...")

    except Exception as e:
        print(f"❌ Ошибка доступа: {e}")

if __name__ == "__main__":
    asyncio.run(open_black_box())
