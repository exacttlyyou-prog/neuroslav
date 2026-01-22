"""
API роутер для работы с Notion.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from urllib.parse import urlparse
import re
from loguru import logger

from app.services.notion_service import NotionService
from app.services.notion_playwright_service import NotionPlaywrightService
from app.services.notion_mcp_service import NotionMCPService
from app.services.notion_background_parser import NotionBackgroundParser
from app.config import get_settings
import httpx
from fastapi import Request

router = APIRouter()


def _extract_notion_page_id(page_url: str) -> Optional[str]:
    """
    Извлечь ID страницы Notion из URL.
    Поддерживает ссылки вида notion.so/<page_id> и notion.so/<title>-<page_id>.
    """
    if not page_url:
        return None
    parsed = urlparse(page_url)
    path = parsed.path.strip("/")
    if not path:
        return None
    # Ищем 32-символьный hex (Notion ID без дефисов)
    match = re.search(r"[0-9a-fA-F]{32}", path)
    if match:
        return match.group(0)
    # Ищем UUID с дефисами
    match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", path)
    if match:
        return match.group(0)
    return None


@router.get("/context/pages")
async def get_ai_context_pages(
    parent_page_id: Optional[str] = Query(None, description="ID родительской страницы"),
    include_content: bool = Query(True, description="Включать ли полный контент страниц"),
    recursive: bool = Query(True, description="Рекурсивно получать вложенные страницы")
):
    """
    Получает список страниц из AI-Context.
    
    Returns:
        Список страниц с контентом
    """
    try:
        notion = NotionService()
        pages = await notion.get_ai_context_pages(
            parent_page_id=parent_page_id,
            include_content=include_content,
            recursive=recursive
        )
        return {
            "pages": pages,
            "count": len(pages),
            "total_content_length": sum(p.get("content_length", 0) for p in pages)
        }
    except Exception as e:
        logger.error(f"Ошибка при получении AI-Context страниц: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages/{page_id}/content")
async def get_page_content(
    page_id: str,
    include_metadata: bool = Query(False, description="Включать метаданные страницы")
):
    """
    Получает полный контент страницы Notion.
    
    Args:
        page_id: ID страницы Notion
        
    Returns:
        Контент страницы
    """
    try:
        notion = NotionService()
        content = await notion.get_page_content(page_id, include_metadata=include_metadata)
        return {
            "page_id": page_id,
            "content": content,
            "content_length": len(content)
        }
    except Exception as e:
        logger.error(f"Ошибка при получении контента страницы {page_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/databases/{database_id}/data-sources")
async def get_database_data_sources(database_id: str):
    """
    Получает data sources из базы данных (для API версии 2025-09-03).
    
    Args:
        database_id: ID базы данных
        
    Returns:
        Список data sources
    """
    try:
        notion = NotionService()
        data_sources = await notion.get_database_data_sources(database_id)
        return {
            "database_id": database_id,
            "data_sources": data_sources,
            "count": len(data_sources)
        }
    except Exception as e:
        logger.error(f"Ошибка при получении data sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_notion(
    q: str = Query(..., description="Поисковый запрос"),
    database_id: Optional[str] = Query(None, description="ID базы данных для поиска")
):
    """
    Ищет в базах данных Notion.
    
    Args:
        q: Поисковый запрос
        database_id: ID базы данных (опционально)
        
    Returns:
        Список найденных страниц
    """
    try:
        notion = NotionService()
        results = await notion.search_in_notion(query=q, database_id=database_id)
        return {"results": results}
    except Exception as e:
        logger.error(f"Ошибка при поиске в Notion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/glossary")
async def get_glossary():
    """
    Получает глоссарий терминов из Notion.
    
    Returns:
        Словарь терминов
    """
    try:
        notion = NotionService()
        glossary = await notion.get_glossary_from_db()
        return {"glossary": glossary}
    except Exception as e:
        logger.error(f"Ошибка при получении глоссария: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/last-meeting")
async def get_last_meeting(
    page_id: Optional[str] = Query(None, description="ID страницы Notion"),
    page_url: Optional[str] = Query(None, description="URL страницы Notion")
):
    """
    Возвращает контент последнего блока со страницы встреч (через API).
    """
    try:
        settings = get_settings()
        resolved_page_id = page_id
        if not resolved_page_id and page_url:
            resolved_page_id = _extract_notion_page_id(page_url)
        if not resolved_page_id:
            resolved_page_id = settings.notion_meeting_page_id
        
        if not resolved_page_id:
            raise HTTPException(status_code=400, detail="Не указан page_id/page_url и NOTION_MEETING_PAGE_ID не установлен")
        
        notion = NotionService()
        result = await notion.get_last_meeting_block(resolved_page_id)
        return {
            "page_id": resolved_page_id,
            "block_id": result.get("block_id"),
            "block_type": result.get("block_type"),
            "content": result.get("content", "")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении последней встречи: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/last-meeting/auto")
async def get_last_meeting_auto(
    page_id: Optional[str] = Query(None, description="ID страницы Notion"),
    process: bool = Query(False, description="Обработать встречу после получения")
):
    """
    Автоматически получает последнюю встречу через Next.js API route (MCP или стандартный API).
    
    Приоритет методов:
    1. Next.js API route /api/notion/fetch-via-mcp (может использовать MCP или стандартный API)
    2. Стандартный Notion API напрямую (fallback)
    3. Playwright (только если другие методы не работают)
    
    Args:
        page_id: ID страницы Notion (если не указан, используется из настроек)
        process: Обработать встречу после получения (запустить workflow)
        
    Returns:
        Контент последней встречи (transcription/саммари) и результаты обработки (если process=True)
    """
    import httpx
    
    try:
        settings = get_settings()
        resolved_page_id = page_id or settings.notion_meeting_page_id
        
        if not resolved_page_id:
            raise HTTPException(status_code=400, detail="Не указан page_id и NOTION_MEETING_PAGE_ID не установлен")
        
        logger.info(f"🚀 Запуск автоматической обработки последней встречи: {resolved_page_id}")
        
        result = None
        method_used = None
        
        # Метод 1: Пробуем через локальный MCP Notion Server (может получить meeting-notes)
        # Делаем это опциональным - если не работает, просто пропускаем
        try:
            logger.info("Пробуем локальный MCP Notion Server...")
            mcp_service = NotionMCPService()
            mcp_result = await mcp_service.fetch_page(resolved_page_id)
            
            if mcp_result:
                # Извлекаем контент из результата MCP
                mcp_content = mcp_service._extract_content_from_mcp_result(mcp_result)
                
                if mcp_content and len(mcp_content.strip()) >= 10:
                    # Используем метод extract_last_meeting_from_mcp_content для парсинга
                    meeting_data = mcp_service.extract_last_meeting_from_mcp_content(mcp_content)
                    
                    if meeting_data:
                        content = meeting_data.get("content", "").strip()
                        meeting_type = meeting_data.get("type", "unknown")
                        
                        if content and len(content) >= 100:
                            result = {
                                "block_id": "",
                                "block_type": f"meeting-notes-{meeting_type}",
                                "content": content,
                                "title": f"Последняя встреча (MCP, {meeting_type})",
                                "has_transcription": meeting_type == "transcript",
                                "has_summary": meeting_type == "summary"
                            }
                            method_used = "nextjs_mcp"  # Используем тот же ключ, что и для Next.js MCP
                            logger.info(f"✅ Получены данные через локальный MCP сервер: {len(content)} символов (тип: {meeting_type})")
                        else:
                            logger.warning(f"MCP вернул контент, но он слишком короткий: {len(content)} символов")
                    else:
                        logger.warning("MCP вернул контент, но meeting-notes блоки не найдены")
                else:
                    logger.warning(f"MCP вернул пустой или слишком короткий контент: {len(mcp_content) if mcp_content else 0} символов")
        except Exception as e:
            logger.warning(f"Локальный MCP сервер недоступен: {e}, пробуем другие методы")
        
        # Метод 2: Пробуем через Next.js API route (может использовать MCP)
        if not result or not result.get("content") or len(result.get("content", "")) < 100:
            try:
                nextjs_url = "http://localhost:3000/api/notion/fetch-via-mcp"
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        nextjs_url,
                        json={"page_id": resolved_page_id},
                        headers={"Content-Type": "application/json"}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        result = {
                            "block_id": data.get("block_id"),
                            "block_type": data.get("block_type"),
                            "content": data.get("content", ""),
                            "title": data.get("title", ""),
                            "has_transcription": data.get("has_transcription", False),
                            "has_summary": data.get("has_summary", False)
                        }
                        method_used = data.get("method", "nextjs_mcp")
                        logger.info(f"✅ Получены данные через Next.js API route: {len(result.get('content', ''))} символов")
                    elif response.status_code in [400, 401, 404]:
                        error_data = response.json()
                        logger.warning(f"Next.js API route вернул ошибку {response.status_code}: {error_data.get('error', 'Unknown error')}")
            except httpx.ConnectError:
                logger.warning("Next.js сервер недоступен (возможно не запущен), пробуем стандартный Notion API")
            except Exception as e:
                logger.warning(f"Next.js API route недоступен: {e}, пробуем стандартный Notion API")
        
        # Метод 2: Fallback на стандартный Notion API
        if not result or not result.get("content") or len(result.get("content", "")) < 100:
            try:
                logger.info("Пробуем стандартный Notion API...")
                notion = NotionService()
                api_result = await notion.get_last_meeting_block(resolved_page_id)
                if api_result.get("content") and len(api_result.get("content", "")) >= 100:
                    result = {
                        "block_id": api_result.get("block_id"),
                        "block_type": api_result.get("block_type"),
                        "content": api_result.get("content", ""),
                        "title": "Последний блок",
                        "has_transcription": False,
                        "has_summary": False
                    }
                    method_used = "notion_api"
                    logger.info(f"✅ Получены данные через стандартный Notion API: {len(result.get('content', ''))} символов")
            except Exception as e:
                logger.warning(f"Стандартный Notion API не сработал: {e}")
        
        # Метод 3: Последний fallback - Playwright (только если другие не сработали)
        if not result or not result.get("content") or len(result.get("content", "")) < 100:
            logger.warning("Используем Playwright как последний fallback (может быть медленно)...")
            try:
                playwright_service = NotionPlaywrightService()
                playwright_result = await playwright_service.get_last_meeting_via_browser(resolved_page_id)
                result = {
                    "block_id": playwright_result.get("block_id"),
                    "block_type": playwright_result.get("block_type"),
                    "content": playwright_result.get("content", ""),
                    "title": playwright_result.get("title", ""),
                    "has_transcription": playwright_result.get("has_transcription", False),
                    "has_summary": playwright_result.get("has_summary", False)
                }
                method_used = "playwright_browser"
                logger.info(f"✅ Получены данные через Playwright: {len(result.get('content', ''))} символов")
            except Exception as e:
                logger.error(f"Playwright также не сработал: {e}")
        
        if not result or not result.get("content") or len(result.get("content", "")) < 100:
            error_detail = (
                "Не удалось получить контент встречи ни одним из методов.\n\n"
                "Возможные причины:\n"
                "1. Страница не найдена или недоступна\n"
                "2. NOTION_TOKEN не установлен или неверный\n"
                "3. Meeting-notes блоки недоступны через стандартный API (требуется MCP Notion)\n\n"
                "Рекомендации:\n"
                "- Проверьте NOTION_TOKEN в переменных окружения\n"
                "- Убедитесь, что страница доступна\n"
                "- Для meeting-notes блоков используйте MCP Notion через Cursor"
            )
            raise HTTPException(
                status_code=500,
                detail=error_detail
            )
        
        response = {
            "page_id": resolved_page_id,
            "block_id": result.get("block_id"),
            "block_type": result.get("block_type"),
            "content": result.get("content", ""),
            "title": result.get("title", ""),
            "method": method_used or "unknown"
        }
        
        # Если нужно обработать встречу
        if process and result.get("content"):
            logger.info("🤖 Запуск обработки встречи...")
            try:
                from app.workflows.meeting_workflow import MeetingWorkflow
                workflow = MeetingWorkflow()
                process_result = await workflow.process_meeting(
                    transcript=result.get("content", ""),
                    notion_page_id=resolved_page_id
                )
                response["processing"] = {
                    "status": "pending_approval" if process_result.get("requires_approval") else "completed",
                    "meeting_id": process_result.get("meeting_id"),
                    "summary": process_result.get("summary"),
                    "participants": process_result.get("participants", []),
                    "projects": process_result.get("projects", []),
                    "action_items": process_result.get("action_items", []),
                    "verification_warnings": process_result.get("verification_warnings", []),
                    "requires_approval": process_result.get("requires_approval", False)
                }
            except Exception as e:
                logger.error(f"Ошибка при обработке встречи: {e}")
                response["processing"] = {
                    "status": "error",
                    "error": str(e)
                }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при автоматическом получении последней встречи: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/parser/status")
async def get_parser_status(request: Request):
    """Возвращает статус фонового парсера страницы встреч."""
    if hasattr(request.app.state, "background_parser"):
        return request.app.state.background_parser.get_status()
    return {"running": False, "error": "Парсер не инициализирован"}


@router.post("/parser/check")
async def manual_parser_check(request: Request):
    """Ручная проверка последнего блока на странице встреч."""
    if not hasattr(request.app.state, "background_parser"):
        raise HTTPException(status_code=503, detail="Парсер не инициализирован")
    
    parser: NotionBackgroundParser = request.app.state.background_parser
    try:
        await parser._check_and_copy_last_block()
        last_block = await parser.get_last_copied_block()
        return {
            "success": True,
            "last_block": last_block,
            "status": parser.get_status()
        }
    except Exception as e:
        logger.error(f"Ошибка при ручной проверке парсера: {e}")
        raise HTTPException(status_code=500, detail=str(e))
