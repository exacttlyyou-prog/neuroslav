import asyncio
import os
import json
from dotenv import load_dotenv
from notion_client import AsyncClient

load_dotenv()

async def inspect_unsupported():
    token = os.getenv("NOTION_TOKEN")
    page_id = os.getenv("NOTION_MEETING_PAGE_ID")
    
    if not token or not page_id:
        print("❌ Ошибка: проверь .env")
        return

    client = AsyncClient(auth=token)
    print(f"🕵️‍♂️ Анализирую страницу: {page_id}")

    try:
        response = await client.blocks.children.list(block_id=page_id)
        blocks = response["results"]

        print(f"📦 Всего блоков: {len(blocks)}")
        
        found_problem = False
        for i, block in enumerate(blocks):
            b_type = block["type"]
            
            # Если блок unsupported, выводим его полную структуру
            if b_type == "unsupported":
                found_problem = True
                print(f"\n🚨 [Блок {i}] ОБНАРУЖЕН UNSUPPORTED:")
                print(json.dumps(block, indent=2, ensure_ascii=False))
            
            # Также проверим, не является ли это Synced Block (частая причина)
            elif b_type == "synced_block":
                print(f"\n🔄 [Блок {i}] Это Synced Block (нужно лезть внутрь)")
            
            else:
                print(f"✅ [Блок {i}] {b_type}")

        if not found_problem:
            print("\n🤷‍♂️ Странно, unsupported блоков не найдено в этом запуске.")

    except Exception as e:
        print(f"❌ Ошибка API: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_unsupported())
