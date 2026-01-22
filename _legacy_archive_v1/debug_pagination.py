import asyncio
import os
from dotenv import load_dotenv
from notion_client import AsyncClient

# Загружаем ключи
load_dotenv()
token = os.getenv("NOTION_TOKEN")
page_id = os.getenv("NOTION_MEETING_PAGE_ID")

async def test_full_read():
    if not token or not page_id:
        print("❌ Ошибка: Проверь .env (нет токена или ID)")
        return

    client = AsyncClient(auth=token)
    print(f"🔄 Подключаюсь к Notion (Page: {page_id})...")

    all_blocks = []
    cursor = None
    
    try:
        # Цикл пагинации (листаем страницы)
        while True:
            response = await client.blocks.children.list(block_id=page_id, start_cursor=cursor)
            blocks = response["results"]
            all_blocks.extend(blocks)
            
            print(f"   📦 Скачано блоков: {len(all_blocks)}...", end="\r")
            
            if not response["has_more"]:
                break
            cursor = response["next_cursor"]
            
        print(f"\n✅ ВСЕГО БЛОКОВ: {len(all_blocks)}")
        
        # Смотрим последние 5 блоков
        print("\n👇 ПОСЛЕДНИЕ 5 БЛОКОВ (Что видит бот):")
        for i, block in enumerate(reversed(all_blocks[-5:])):
            b_type = block["type"]
            content = "..."
            # Пытаемся достать текст
            if "rich_text" in block.get(b_type, {}):
                text_arr = block[b_type]["rich_text"]
                content = "".join([t["plain_text"] for t in text_arr])
            
            print(f"[{i+1}] Тип: {b_type} | Текст: '{content}'")

    except Exception as e:
        print(f"\n❌ ОШИБКА API: {e}")

if __name__ == "__main__":
    asyncio.run(test_full_read())
