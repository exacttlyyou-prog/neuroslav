"""
Тест Notion AI API для получения transcription блоков.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from integrations.notion_ai_api import NotionAIApiClient
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="DEBUG", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

PAGE_IDS = [
    "2edfa7fd637180b98715fa9f348f90f9",
    "ce32758331a5406694f86b8bd292605a",
]

async def main():
    print("🚀 Тест Notion AI API для получения transcription блоков...\n")
    
    ai_client = NotionAIApiClient()
    
    for page_id in PAGE_IDS:
        print(f"{'='*60}")
        print(f"📄 Страница: {page_id}")
        print(f"{'='*60}\n")
        
        try:
            # Пробуем получить данные через AI API
            data = await ai_client.get_page_with_ai_content(page_id)
            
            if data:
                print(f"✅ Данные получены!")
                print(f"   Transcription блоков: {len(data.get('transcription_blocks', []))}")
                print(f"   Всего блоков: {len(data.get('blocks', []))}")
                
                # Пробуем извлечь контент
                content = await ai_client.get_transcription_content(page_id)
                if content:
                    print(f"   Контент: {len(content)} символов")
                    print(f"\n   Первые 500 символов:\n   {content[:500]}...\n")
                else:
                    print("   ❌ Контент не извлечен\n")
            else:
                print("❌ Данные не получены\n")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}\n")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
