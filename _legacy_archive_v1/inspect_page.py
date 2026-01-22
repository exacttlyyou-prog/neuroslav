import asyncio

import os

from dotenv import load_dotenv

from notion_client import AsyncClient



load_dotenv()



async def inspect_page():

    page_id = os.getenv("NOTION_MEETING_PAGE_ID")

    token = os.getenv("NOTION_TOKEN")

    

    if not page_id or not token:

        print("❌ Нет токена или ID страницы в .env")

        return



    print(f"🔍 Сканирую страницу: {page_id}...")

    notion = AsyncClient(auth=token)



    try:

        # Получаем блоки (с учетом пагинации, если страница длинная)

        blocks = []

        cursor = None

        while True:

            response = await notion.blocks.children.list(block_id=page_id, start_cursor=cursor)

            blocks.extend(response["results"])

            if not response["has_more"]:

                break

            cursor = response["next_cursor"]

        

        print(f"✅ Всего блоков на странице: {len(blocks)}")

        

        # Смотрим последние 10 блоков

        print("\n👇 ПОСЛЕДНИЕ 10 БЛОКОВ (Что видит бот):")

        print("-" * 50)

        

        for i, block in enumerate(blocks[-10:]):

            b_type = block["type"]

            b_id = block["id"]

            content = "..."

            

            # Пытаемся достать текст

            if b_type in block and "rich_text" in block[b_type]:

                text_list = block[b_type]["rich_text"]

                content = "".join([t["plain_text"] for t in text_list])

            

            # Маркер пустоты

            is_empty = len(content.strip()) == 0

            status_icon = "❌ ПУСТО" if is_empty else f"✅ ТЕКСТ ({len(content)} симв.)"

            

            print(f"[{i}] Тип: {b_type:<15} | {status_icon} | '{content}'")



        print("-" * 50)



    except Exception as e:

        print(f"❌ Ошибка Notion API: {e}")



if __name__ == "__main__":

    asyncio.run(inspect_page())

