"""
Тестовый скрипт для проверки работы с Notion страницей через наш агент.
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))

from core.ai_service import AIService
from core.config import get_settings
from services.notion_service import NotionService
from core.schemas import MeetingAnalysis


async def test_analyze_notion_page():
    """Тестирует анализ страницы Notion через наш агент."""
    page_id = "2edfa7fd637180b98715fa9f348f90f9"
    page_url = "https://www.notion.so/2026-2edfa7fd637180b98715fa9f348f90f9"
    
    print(f"🔍 Получение контента страницы Notion: {page_id}")
    
    try:
        # Получаем контент через NotionService
        notion = NotionService()
        content = await notion.get_page_content(page_id)
        
        print(f"✅ Получен контент, длина: {len(content)} символов")
        print(f"\n📄 Первые 500 символов:\n{content[:500]}...\n")
        
        # Анализируем через Gemini 3.0 Flash
        print("🤖 Анализ через Gemini 3.0 Flash...")
        ai_service = AIService()
        analysis = await ai_service.analyze_meeting(content, MeetingAnalysis)
        
        print("\n" + "="*60)
        print("📋 РЕЗУЛЬТАТЫ АНАЛИЗА")
        print("="*60)
        print(f"\n📝 Саммари:\n{analysis.summary_md}\n")
        print(f"\n✅ Задач извлечено: {len(analysis.action_items)}")
        
        if analysis.action_items:
            print("\n📌 Задачи:")
            for i, item in enumerate(analysis.action_items, 1):
                priority_emoji = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}.get(item.priority, '⚪')
                assignee = f" ({item.assignee})" if item.assignee else ""
                print(f"  {i}. {priority_emoji} {item.text}{assignee}")
        
        if analysis.meeting_date_proposal:
            print(f"\n📅 Предложенная дата встречи: {analysis.meeting_date_proposal}")
        
        if analysis.risk_assessment:
            print(f"\n⚠️  Риски: {analysis.risk_assessment}")
        
        print("\n" + "="*60)
        print("✅ Анализ завершен успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_analyze_notion_page())

