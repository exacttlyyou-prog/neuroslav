#!/usr/bin/env python3
"""
Скрипт для получения контента из Notion через MCP и сохранения в файл.
Запускайте этот скрипт для получения свежих данных из Notion.
"""
import json
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from dotenv import load_dotenv
from loguru import logger

# Загружаем переменные окружения
load_dotenv()

# Импорт telegram с fallback
try:
    from telegram import Bot
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Bot = None

from core.config import get_settings
from services.notion_service import NotionService

async def get_mcp_content_via_cursor():
    """
    Получает контент страницы через MCP Notion и сохраняет в файл.
    """
    print("🚀 Получение контента через MCP Notion...")

    try:
        settings = get_settings()

        if not settings.notion_meeting_page_id:
            print("❌ Ошибка: NOTION_MEETING_PAGE_ID не установлен в .env")
            return False

        page_id = settings.notion_meeting_page_id
        print(f"🔍 Получаем данные страницы: {page_id}")

        # Инструкции для пользователя
        print("\n📋 Для получения данных выполните в терминале Cursor:")
        print(f"""
curl -X POST http://localhost:3000/mcp/notion/fetch \\
  -H "Content-Type: application/json" \\
  -d '{{"id": "{page_id}"}}'
        """)

        print("\n💡 Или используйте MCP инструмент:")
        print("1. В Cursor откройте Command Palette (Cmd+Shift+P)")
        print("2. Найдите 'MCP: Fetch Notion Page'")
        print(f"3. Введите ID страницы: {page_id}")
        print("4. Скопируйте JSON результат")

        # Ждем пользовательского ввода
        print("\n📝 Вставьте сюда JSON ответ от MCP Notion:")
        print("(Или нажмите Enter для отмены)")

        json_input = ""
        while True:
            try:
                line = input()
                if line.strip() == "":
                    break
                json_input += line + "\n"
            except EOFError:
                break

        if not json_input.strip():
            print("❌ Отменено пользователем")
            return False

        try:
            # Парсим JSON
            mcp_data = json.loads(json_input)

            # Сохраняем в файл
            mcp_file = root_dir / "mcp_response.json"
            with open(mcp_file, 'w', encoding='utf-8') as f:
                json.dump(mcp_data, f, ensure_ascii=False, indent=2)

            print(f"✅ Данные сохранены в файл: {mcp_file}")
            print(f"📊 Размер файла: {len(json_input)} символов")

            return True

        except json.JSONDecodeError as e:
            print(f"❌ Ошибка парсинга JSON: {e}")
            return False

    except Exception as e:
        logger.error(f"Ошибка при получении MCP контента: {e}")
        print(f"❌ Ошибка: {e}")
        return False

async def test_mcp_content():
    """
    Тестирует сохраненный MCP контент.
    """
    print("🧪 Тестирование сохраненного MCP контента...")

    mcp_file = root_dir / "mcp_response.json"
    if not mcp_file.exists():
        print("❌ Файл mcp_response.json не найден")
        print("💡 Сначала получите данные через get_mcp_content_via_cursor()")
        return False

    try:
        with open(mcp_file, 'r', encoding='utf-8') as f:
            mcp_data = json.load(f)

        # Извлекаем контент последней встречи
        content = extract_latest_meeting_from_mcp(mcp_data)

        if content and len(content.strip()) >= 50:
            print("✅ Контент успешно извлечен!")
            print(f"📝 Длина контента: {len(content)} символов")
            print("\n📄 Предпросмотр контента:")
            print("-" * 50)
            preview = content[:500] + "..." if len(content) > 500 else content
            print(preview)
            print("-" * 50)
            return True
        else:
            print("❌ Контент не найден или слишком короткий")
            return False

    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        return False

def extract_latest_meeting_from_mcp(mcp_data: dict) -> str:
    """
    Извлекает контент последней встречи из MCP Notion ответа.
    """
    try:
        # Получаем текст страницы
        page_text = mcp_data.get('text', '')

        # Ищем все блоки meeting-notes
        import re
        meeting_notes_pattern = r'<meeting-notes>(.*?)</meeting-notes>'
        meetings = re.findall(meeting_notes_pattern, page_text, re.DOTALL)

        if not meetings:
            return ""

        # Берем последний блок (самая свежая встреча)
        latest_meeting = meetings[-1]

        # Извлекаем контент из summary и transcript
        content_parts = []

        # Summary
        summary_match = re.search(r'<summary>(.*?)</summary>', latest_meeting, re.DOTALL)
        if summary_match:
            summary_text = summary_match.group(1).strip()
            # Очищаем от HTML тегов для лучшего анализа
            summary_clean = re.sub(r'<[^>]+>', '', summary_text)
            content_parts.append(f"Summary:\n{summary_clean}")

        # Transcript
        transcript_match = re.search(r'<transcript>(.*?)</transcript>', latest_meeting, re.DOTALL)
        if transcript_match:
            transcript_text = transcript_match.group(1).strip()
            # Очищаем от HTML тегов
            transcript_clean = re.sub(r'<[^>]+>', '', transcript_text)
            content_parts.append(f"Transcript:\n{transcript_clean}")

        # Notes (если есть)
        notes_match = re.search(r'<notes>(.*?)</notes>', latest_meeting, re.DOTALL)
        if notes_match:
            notes_text = notes_match.group(1).strip()
            if notes_text and not notes_text.startswith('<empty-block'):
                notes_clean = re.sub(r'<[^>]+>', '', notes_text)
                content_parts.append(f"Notes:\n{notes_clean}")

        final_content = "\n\n".join(content_parts)

        return final_content.strip()

    except Exception as e:
        logger.error(f"Ошибка при извлечении контента из MCP данных: {e}")
        return ""

async def main():
    """
    Главная функция.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Получение контента из Notion через MCP")
    parser.add_argument("--get", action="store_true", help="Получить новые данные через MCP")
    parser.add_argument("--test", action="store_true", help="Протестировать сохраненный контент")

    args = parser.parse_args()

    if args.get:
        await get_mcp_content_via_cursor()
    elif args.test:
        await test_mcp_content()
    else:
        print("Использование:")
        print("  python get_mcp_content.py --get    # Получить данные через MCP")
        print("  python get_mcp_content.py --test   # Протестировать сохраненный контент")
        print("\nПримеры:")
        print("  python get_mcp_content.py --get")
        print("  python get_mcp_content.py --test")

if __name__ == "__main__":
    asyncio.run(main())