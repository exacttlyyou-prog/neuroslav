#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы NotionPlaywrightService.
Запуск: python -m app.scripts.test_notion_playwright
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в пути
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.services.notion_playwright_service import NotionPlaywrightService
from app.config import get_settings
from loguru import logger


async def main():
    """Тестирует получение последней встречи через браузер."""
    logger.info("🚀 Запуск теста NotionPlaywrightService...")
    
    settings = get_settings()
    page_id = settings.notion_meeting_page_id
    
    if not page_id:
        logger.error("❌ NOTION_MEETING_PAGE_ID не установлен в переменных окружения")
        logger.info("💡 Установите переменную: export NOTION_MEETING_PAGE_ID=your-page-id")
        return
    
    logger.info(f"📄 Используем страницу: {page_id}")
    
    try:
        service = NotionPlaywrightService()
        
        if not service.playwright_available:
            logger.error("❌ Playwright не установлен")
            logger.info("💡 Установите: pip install playwright && playwright install chromium")
            return
        
        logger.info("🌐 Открываем Notion в браузере...")
        result = await service.get_last_meeting_via_browser(page_id)
        
        logger.info("\n" + "="*60)
        logger.info("✅ РЕЗУЛЬТАТ:")
        logger.info("="*60)
        logger.info(f"Заголовок: {result.get('title', 'N/A')}")
        logger.info(f"Тип блока: {result.get('block_type', 'N/A')}")
        logger.info(f"ID блока: {result.get('block_id', 'N/A')}")
        logger.info(f"Transcription: {result.get('has_transcription', False)}")
        logger.info(f"Summary: {result.get('has_summary', False)}")
        logger.info(f"Длина контента: {len(result.get('content', ''))} символов")
        logger.info("\n" + "-"*60)
        logger.info("КОНТЕНТ:")
        logger.info("-"*60)
        content = result.get('content', '')
        if content:
            # Показываем первые 1000 символов
            preview = content[:1000]
            logger.info(preview)
            if len(content) > 1000:
                logger.info(f"\n... (еще {len(content) - 1000} символов)")
        else:
            logger.warning("Контент пуст!")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        import traceback
        logger.debug(traceback.format_exc())


if __name__ == "__main__":
    asyncio.run(main())
