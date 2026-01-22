"""
Тест прямого подключения к MCP Notion через Python SDK.
Пробуем запустить MCP сервер через subprocess (npx) и общаться с ним через stdio.
"""
import asyncio
import os
from dotenv import load_dotenv
from mcp import ClientSession, stdio_client, StdioServerParameters
from loguru import logger

load_dotenv()

async def test_mcp_via_subprocess():
    """Пробуем запустить MCP Notion сервер через npx и подключиться к нему."""
    token = os.getenv("NOTION_TOKEN")
    page_id = os.getenv("NOTION_MEETING_PAGE_ID")
    
    if not token or not page_id:
        print("❌ Нет токена или page_id")
        return
    
    print(f"🔌 Запуск MCP Notion через subprocess...")
    print(f"📄 Page ID: {page_id}")
    
    try:
        # Пробуем запустить официальный MCP Notion сервер через npx
        # Согласно документации, это @notionhq/notion-mcp-server или @modelcontextprotocol/server-notion
        server_configs = [
            StdioServerParameters(
                command="npx",
                args=["-y", "@notionhq/notion-mcp-server"],
                env={**os.environ, "NOTION_TOKEN": token}
            ),
            StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-notion"],
                env={**os.environ, "NOTION_TOKEN": token}
            ),
        ]
        
        for server_config in server_configs:
            cmd_str = f"{server_config.command} {' '.join(server_config.args)}"
            print(f"\n🔹 Пробуем команду: {cmd_str}")
            try:
                # Запускаем MCP сервер через stdio
                async with stdio_client(server_config) as (read, write):
                    async with ClientSession(read, write) as session:
                        # Инициализация
                        init_result = await session.initialize()
                        print(f"✅ Инициализация успешна: {init_result}")
                        
                        # Получаем список доступных инструментов
                        tools = await session.list_tools()
                        print(f"📋 Доступные инструменты: {[t.name for t in tools.tools]}")
                        
                        # Ищем инструмент notion-fetch
                        fetch_tool = None
                        for tool in tools.tools:
                            if tool.name == "notion-fetch":
                                fetch_tool = tool
                                break
                        
                        if not fetch_tool:
                            print("❌ Инструмент notion-fetch не найден")
                            print(f"Доступные инструменты: {[t.name for t in tools.tools]}")
                            continue
                        
                        print(f"🔧 Используем инструмент: {fetch_tool.name}")
                        
                        # Вызываем инструмент с правильным форматом
                        result = await session.call_tool(
                            "notion-fetch",
                            arguments={"id": page_id}
                        )
                        
                        print(f"✅ Успех! Результат получен")
                        print(f"📝 Тип результата: {type(result)}")
                        
                        # Извлекаем текст из результата
                        text_content = ""
                        if hasattr(result, 'content'):
                            for content_item in result.content:
                                if hasattr(content_item, 'text'):
                                    text_content += content_item.text
                                elif isinstance(content_item, dict) and 'text' in content_item:
                                    text_content += content_item['text']
                                else:
                                    text_content += str(content_item)
                        
                        if text_content:
                            print(f"📄 Длина контента: {len(text_content)} символов")
                            print(f"📝 Первые 500 символов:\n{text_content[:500]}...")
                            
                            # Проверяем наличие meeting-notes
                            if "<meeting-notes>" in text_content:
                                print("✅ Найдены meeting-notes блоки!")
                            else:
                                print("⚠️  meeting-notes блоки не найдены")
                        else:
                            print(f"📄 Результат: {result}")
                        
                        return result
                        
            except FileNotFoundError:
                print(f"❌ Команда не найдена: {cmd[0]}")
                continue
            except Exception as e:
                print(f"❌ Ошибка при выполнении команды: {e}")
                logger.exception(e)
                continue
        
        print("\n❌ Все варианты не сработали")
        print("💡 Возможно, нужна установка Node.js или другой способ авторизации")
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logger.exception(e)

if __name__ == "__main__":
    asyncio.run(test_mcp_via_subprocess())
