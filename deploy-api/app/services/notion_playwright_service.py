"""
Сервис для автоматизации работы с Notion через браузер (Playwright).
Используется для получения контента последней встречи, включая transcription блоки.
"""
import asyncio
from typing import Optional, Dict, Any
from loguru import logger
from pathlib import Path

from app.config import get_settings


class NotionPlaywrightService:
    """Автоматизация работы с Notion через браузер с помощью Playwright."""
    
    def __init__(self):
        settings = get_settings()
        self.meeting_page_id = settings.notion_meeting_page_id
        
        # Получаем токен авторизации для Notion
        self.auth_token = settings.notion_mcp_token or settings.notion_token
        
        # Путь к сохраненному состоянию сессии (Session Replay паттерн)
        # Согласно техническому отчету: используем предварительно сохраненную сессию
        data_dir = Path(__file__).parent.parent.parent / "data"
        self.auth_file = data_dir / "notion_auth.json"
        
        # Проверяем наличие сохраненной сессии
        if self.auth_file.exists():
            logger.info(f"✅ Найдено сохраненное состояние сессии: {self.auth_file}")
        else:
            logger.warning(
                f"⚠️  Сохраненное состояние сессии не найдено: {self.auth_file}\n"
                f"   Запустите скрипт настройки: python -m app.scripts.setup_notion_auth"
            )
        
        # Проверяем наличие Playwright
        try:
            from playwright.async_api import async_playwright
            self.playwright_available = True
        except ImportError:
            logger.warning("Playwright не установлен. Установите: pip install playwright && playwright install webkit")
            self.playwright_available = False
    
    async def get_last_meeting_via_browser(self, page_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Главный метод: открывает Notion в приложении или дефолтном браузере,
        ждет пока пользователь скопирует текст, затем получает из буфера обмена.
        
        Args:
            page_id: ID страницы Notion (если None, используется из настроек)
            
        Returns:
            Словарь с контентом последнего блока:
            {
                "block_id": str,
                "block_type": str,
                "content": str,
                "title": str
            }
        """
        import platform
        import subprocess
        
        if platform.system() != "Darwin":
            raise RuntimeError("Этот метод работает только на macOS")
        
        resolved_page_id = page_id or self.meeting_page_id
        if not resolved_page_id:
            raise ValueError("Не указан page_id и NOTION_MEETING_PAGE_ID не установлен")
        
        # Формируем URL страницы
        clean_id = resolved_page_id.replace('-', '')
        page_url = f"https://www.notion.so/{clean_id}"
        notion_url = f"notion://www.notion.so/{clean_id}"
        
        logger.info(f"📱 Открываем Notion: {page_url}")
        
        try:
            # Пробуем открыть в приложении Notion
            try:
                logger.info("📱 Пробуем открыть в приложении Notion...")
                subprocess.run(["open", "-a", "Notion", notion_url], check=False, timeout=5)
                logger.info("✅ Notion приложение открыто (или URL открыт в браузере)")
            except Exception as e:
                logger.debug(f"Не удалось открыть в приложении: {e}, открываем в браузере...")
                # Fallback: открываем в дефолтном браузере
                subprocess.run(["open", page_url], check=False, timeout=5)
                logger.info("✅ URL открыт в дефолтном браузере")
            
            # Даем время пользователю открыть страницу и прокрутить до нужного места
            logger.info("")
            logger.info("=" * 60)
            logger.info("📋 ИНСТРУКЦИЯ:")
            logger.info("=" * 60)
            logger.info("1. Откройте страницу встреч в Notion")
            logger.info("2. Прокрутите до последней встречи")
            logger.info("3. Найдите транскрипцию или саммари")
            logger.info("4. Выделите весь нужный текст (Cmd+A или вручную)")
            logger.info("5. Скопируйте текст (Cmd+C)")
            logger.info("=" * 60)
            logger.info("")
            logger.info("⏳ Ожидаем копирование текста (максимум 15 секунд)...")
            logger.info("💡 После копирования скрипт автоматически получит текст из буфера обмена")
            
            # Опрашиваем буфер обмена каждые 2 секунды, максимум 15 секунд
            clipboard_text = None
            max_wait_time = 15  # Максимальное время ожидания в секундах
            poll_interval = 2  # Интервал опроса в секундах
            max_attempts = max_wait_time // poll_interval  # Количество попыток
            
            for attempt in range(max_attempts):
                try:
                    result = subprocess.run(
                        ["pbpaste"],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0 and result.stdout and len(result.stdout.strip()) > 100:
                        clipboard_text = result.stdout
                        logger.info(f"✅ Получен текст из буфера обмена: {len(clipboard_text)} символов (попытка {attempt + 1})")
                        break
                    else:
                        logger.debug(f"Попытка {attempt + 1}/{max_attempts}: текст еще не скопирован или слишком короткий")
                except Exception as e:
                    logger.debug(f"Попытка {attempt + 1} получить буфер обмена: {e}")
                
                # Ждем перед следующей попыткой (кроме последней)
                if attempt < max_attempts - 1:
                    await asyncio.sleep(poll_interval)
            
            if not clipboard_text or len(clipboard_text.strip()) < 100:
                raise RuntimeError(
                    f"Не удалось получить текст из буфера обмена за {max_wait_time} секунд. "
                    "Убедитесь, что вы скопировали текст (Cmd+C) с достаточным количеством контента (минимум 100 символов)."
                )
            
            # Обрабатываем скопированный текст
            lines = clipboard_text.split('\n')
            transcription_start = -1
            summary_start = -1
            
            for i, line in enumerate(lines):
                line_lower = line.lower()
                if ('transcript' in line_lower or 'транскрипт' in line_lower) and transcription_start == -1:
                    transcription_start = i
                if ('summary' in line_lower or 'саммари' in line_lower or 'резюме' in line_lower) and summary_start == -1:
                    summary_start = i
            
            # Определяем тип контента
            if transcription_start >= 0:
                content = '\n'.join(lines[transcription_start:]).strip()
                block_type = "transcription"
                title = "Последняя транскрипция"
                has_transcription = True
                has_summary = False
            elif summary_start >= 0:
                content = '\n'.join(lines[summary_start:]).strip()
                block_type = "summary"
                title = "Последнее саммари"
                has_transcription = False
                has_summary = True
            else:
                # Берем весь текст или последние 20000 символов
                if len(clipboard_text) > 20000:
                    content = clipboard_text[-20000:].strip()
                else:
                    content = clipboard_text.strip()
                block_type = "copied_text"
                title = content.split('\n')[0][:100] if content else "Скопированный текст"
                has_transcription = transcription_start >= 0
                has_summary = summary_start >= 0
            
            if len(content) < 50:
                raise RuntimeError(f"Получен слишком короткий текст ({len(content)} символов). Убедитесь, что вы скопировали правильный контент.")
            
            return {
                "block_id": "",
                "block_type": block_type,
                "content": content,
                "title": title,
                "has_transcription": has_transcription,
                "has_summary": has_summary
            }
                    
        except Exception as e:
            logger.error(f"Ошибка при получении последней встречи: {e}")
            raise
    
    async def _launch_browser(self, playwright, headless: bool = True):
        """Запускает браузер Safari (webkit) - ТОЛЬКО Safari, никакого Chrome."""
        mode = "headless" if headless else "видимый"
        logger.info(f"🌐 Запускаем Safari (webkit) в режиме {mode}...")
        try:
            browser = await playwright.webkit.launch(headless=headless)
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
            )
            
            # Устанавливаем cookies авторизации, если есть токен
            if self.auth_token:
                try:
                    cookies = [
                        {
                            "name": "token_v2",
                            "value": self.auth_token,
                            "domain": ".notion.so",
                            "path": "/"
                        }
                    ]
                    await browser_context.add_cookies(cookies)
                    logger.info("✅ Установлены cookies авторизации Notion")
                except Exception as e:
                    logger.warning(f"Не удалось установить cookies авторизации: {e}")
            
            logger.info(f"✅ Safari запущен (режим: {mode})")
            return browser_context
        except Exception as e:
            logger.error(f"❌ Не удалось запустить Safari: {e}")
            logger.error("Установите webkit: playwright install webkit")
            raise RuntimeError(f"Не удалось запустить Safari (webkit). Установите: playwright install webkit. Ошибка: {e}")
    
    async def _wait_for_content(self, page):
        """Ждет загрузки контента страницы."""
        try:
            await page.wait_for_selector(
                ".notion-page-content, [data-content-editable-root], .notion-page-view, .notion-page-body, [class*='notion-page']",
                timeout=15000
            )
            logger.debug("Контент страницы найден")
        except Exception:
            logger.debug("Селектор контента не найден, продолжаем...")
        
        # Дополнительное ожидание для динамической загрузки
        await asyncio.sleep(5)
    
    async def _scroll_to_last_block(self, page):
        """
        Прокручивает страницу до последнего блока снизу.
        
        Реализует алгоритм скроллинга согласно техническому отчету:
        - Прокручивает вниз шагами по 800px
        - Ждет 500мс для загрузки чанков данных
        - Повторяет, пока нужный селектор не появится в DOM
        """
        logger.info("📜 Прокручиваем до последнего блока (умный скроллинг)...")
        
        # Согласно техническому отчету: алгоритм виртуализации
        # Notion - это React-приложение с Lazy Loading
        # Блоки ниже видимой области физически отсутствуют в DOM
        
        scroll_step = 800  # Шаг прокрутки в пикселях
        wait_time = 0.5  # Ожидание между шагами (500мс)
        max_scrolls = 20  # Максимальное количество шагов
        
        # Ищем селектор "AI Summary" или "Summary" во время прокрутки
        target_selectors = [
            'div[data-block-id]',
            'div:has-text("AI Summary")',
            'div:has-text("Summary")',
            'div:has-text("Саммари")',
            'div:has-text("Транскрипт")',
            'div:has-text("Transcript")'
        ]
        
        found_target = False
        scroll_attempts = 0
        last_height = 0
        
        while scroll_attempts < max_scrolls and not found_target:
            # Прокручиваем вниз на высоту окна
            current_scroll = scroll_attempts * scroll_step
            await page.evaluate(f"window.scrollTo(0, {current_scroll})")
            
            # Ждем сетевой активности (загрузка чанков данных)
            await asyncio.sleep(wait_time)
            
            # Проверяем, появился ли нужный селектор в DOM
            try:
                # Используем locator с фильтром по тексту (согласно отчету)
                for selector in target_selectors:
                    if selector.startswith('div:has-text'):
                        # Для селекторов с текстом используем filter
                        elements = await page.locator('div[data-block-id]').filter(
                            has_text=selector.split('"')[1]
                        ).count()
                        if elements > 0:
                            found_target = True
                            logger.debug(f"Найден целевой элемент: {selector}")
                            break
                    else:
                        # Для обычных селекторов
                        count = await page.locator(selector).count()
                        if count > 0:
                            found_target = True
                            logger.debug(f"Найден целевой элемент: {selector}")
                            break
            except Exception as e:
                logger.debug(f"Ошибка при проверке селекторов: {e}")
            
            # Проверяем, изменилась ли высота страницы
            current_height = await page.evaluate("document.body.scrollHeight")
            if current_height == last_height and scroll_attempts > 5:
                # Высота не изменилась несколько раз подряд - весь контент загружен
                logger.debug("Высота страницы не изменилась, контент загружен")
                break
            last_height = current_height
            
            scroll_attempts += 1
        
        # Финальная прокрутка до конца
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)  # Финальное ожидание для загрузки transcription блоков
        
        logger.debug(f"Умный скроллинг завершен после {scroll_attempts} попыток (найден целевой элемент: {found_target})")
    
    async def _copy_last_block_content(self, page) -> Dict[str, Any]:
        """Копирует контент последней встречи (transcription или саммари)."""
        logger.info("📋 Ищем контент последней встречи...")
        
        # Метод 1: Ищем последнюю встречу и её transcription/саммари блоки
        js_code = """
        () => {
            // Ищем все страницы-встречи (обычно это блоки с заголовками дат)
            const allBlocks = Array.from(document.querySelectorAll('[data-block-id]'));
            
            // Ищем последнюю встречу - обычно это страница с заголовком даты
            // В Notion встречи часто оформлены как отдельные страницы или большие блоки
            let lastMeetingBlock = null;
            let lastMeetingTitle = '';
            
            // Ищем блоки, которые выглядят как заголовки встреч (содержат дату)
            const datePattern = /(\\d{1,2}[\\/\\.-]\\d{1,2}[\\/\\.-]\\d{2,4}|\\d{4}[\\/\\.-]\\d{1,2}[\\/\\.-]\\d{1,2}|январ|феврал|март|апрел|май|июн|июл|август|сентябр|октябр|ноябр|декабр|встреча|meeting|standup|стендап)/i;
            
            // Сначала ищем все заголовки встреч
            const meetingHeaders = [];
            for (let i = 0; i < allBlocks.length; i++) {
                const block = allBlocks[i];
                const blockText = block.innerText || block.textContent || '';
                if (blockText && (datePattern.test(blockText) || 
                    blockText.toLowerCase().includes('встреча') || 
                    blockText.toLowerCase().includes('meeting') ||
                    blockText.toLowerCase().includes('стендап'))) {
                    meetingHeaders.push({ index: i, block: block, text: blockText.trim() });
                }
            }
            
            // Берем последний заголовок встречи
            if (meetingHeaders.length > 0) {
                const lastHeader = meetingHeaders[meetingHeaders.length - 1];
                lastMeetingTitle = lastHeader.text.substring(0, 200);
                const startIndex = lastHeader.index;
                
                // Ищем все блоки после этого заголовка до следующего заголовка или до конца
                let meetingContent = [];
                let foundTranscription = false;
                let foundSummary = false;
                
                // Определяем конец встречи (следующий заголовок или конец страницы)
                const nextHeaderIndex = meetingHeaders.length > 1 ? 
                    meetingHeaders[meetingHeaders.length - 2].index : allBlocks.length;
                
                // Собираем контент всех блоков от заголовка до следующего заголовка
                for (let j = startIndex; j < nextHeaderIndex && j < allBlocks.length; j++) {
                    const contentBlock = allBlocks[j];
                    const contentText = contentBlock.innerText || contentBlock.textContent || '';
                    
                    // Ищем transcription или саммари блоки
                    const blockType = contentBlock.getAttribute('data-block-type') || '';
                    const className = contentBlock.className || '';
                    const ariaLabel = contentBlock.getAttribute('aria-label') || '';
                    const contentLower = contentText.toLowerCase();
                    
                    const isTranscription = blockType.includes('transcription') || 
                                           className.toLowerCase().includes('transcription') ||
                                           ariaLabel.toLowerCase().includes('transcription') ||
                                           contentLower.includes('transcript') ||
                                           contentLower.includes('транскрипт');
                    
                    const isSummary = blockType.includes('summary') || 
                                     className.toLowerCase().includes('summary') ||
                                     ariaLabel.toLowerCase().includes('summary') ||
                                     contentLower.includes('саммари') ||
                                     contentLower.includes('резюме') ||
                                     contentLower.includes('summary');
                    
                    if (isTranscription || isSummary) {
                        if (contentText && contentText.length > 100) {
                            meetingContent.push(contentText.trim());
                            if (isTranscription) foundTranscription = true;
                            if (isSummary) foundSummary = true;
                        }
                    } else if (contentText && contentText.length > 50) {
                        // Добавляем и другие блоки, если они достаточно большие
                        meetingContent.push(contentText.trim());
                    }
                }
                
                if (meetingContent.length > 0) {
                    const fullContent = meetingContent.join('\\n\\n');
                    return {
                        blockId: lastHeader.block.getAttribute('data-block-id') || '',
                        blockType: 'meeting',
                        content: fullContent,
                        title: lastMeetingTitle,
                        hasTranscription: foundTranscription,
                        hasSummary: foundSummary
                    };
                }
            }
            
            // Метод 2: Если не нашли структурированную встречу, ищем transcription блоки напрямую
            const transcriptionBlocks = [];
            const transcriptionSelectors = [
                '[data-block-type*="transcription"]',
                '[data-block-type*="meeting-notes"]',
                '[class*="transcription"]',
                '[class*="meeting-notes"]',
                '[aria-label*="transcription"]'
            ];
            
            for (const selector of transcriptionSelectors) {
                const blocks = document.querySelectorAll(selector);
                for (const block of blocks) {
                    const text = block.innerText || block.textContent || '';
                    if (text && text.length > 100) {
                        transcriptionBlocks.push(text.trim());
                    }
                }
                if (transcriptionBlocks.length > 0) break;
            }
            
            if (transcriptionBlocks.length > 0) {
                // Берем последний transcription блок
                const lastTranscription = transcriptionBlocks[transcriptionBlocks.length - 1];
                return {
                    blockId: '',
                    blockType: 'transcription',
                    content: lastTranscription,
                    title: 'Последняя транскрипция',
                    hasTranscription: true,
                    hasSummary: false
                };
            }
            
            // Метод 3: Fallback - берем последние большие блоки
            const largeBlocks = allBlocks.filter(block => {
                const text = block.innerText || block.textContent || '';
                return text && text.length > 500;
            });
            
            if (largeBlocks.length > 0) {
                const lastLargeBlock = largeBlocks[largeBlocks.length - 1];
                const content = lastLargeBlock.innerText || lastLargeBlock.textContent || '';
                return {
                    blockId: lastLargeBlock.getAttribute('data-block-id') || '',
                    blockType: lastLargeBlock.getAttribute('data-block-type') || 'unknown',
                    content: content.trim(),
                    title: content.split('\\n')[0].substring(0, 100),
                    hasTranscription: false,
                    hasSummary: false
                };
            }
            
            return null;
        }
        """
        
        try:
            result = await page.evaluate(js_code)
            if result and result.get('content'):
                logger.info(f"✅ Получен контент последней встречи: {len(result['content'])} символов")
                logger.info(f"   Заголовок: {result.get('title', 'N/A')}")
                logger.info(f"   Transcription: {result.get('hasTranscription', False)}, Summary: {result.get('hasSummary', False)}")
                return {
                    "block_id": result.get('blockId', ''),
                    "block_type": result.get('blockType', 'unknown'),
                    "content": result.get('content', ''),
                    "title": result.get('title', ''),
                    "has_transcription": result.get('hasTranscription', False),
                    "has_summary": result.get('hasSummary', False)
                }
        except Exception as e:
            logger.warning(f"Ошибка получения через JavaScript: {e}")
        
        # Метод 4: Fallback - получаем весь текст страницы и берем последнюю часть
        try:
            all_text = await page.inner_text("body")
            if all_text:
                # Ищем в тексте transcription или саммари
                lines = all_text.split('\\n')
                transcription_start = -1
                summary_start = -1
                
                for i, line in enumerate(lines):
                    if 'transcript' in line.lower() or 'транскрипт' in line.lower():
                        transcription_start = i
                    if 'summary' in line.lower() or 'саммари' in line.lower() or 'резюме' in line.lower():
                        summary_start = i
                
                # Берем контент после найденных меток
                if transcription_start >= 0:
                    content = '\\n'.join(lines[transcription_start:])
                    logger.info(f"✅ Найден transcription в тексте: {len(content)} символов")
                    return {
                        "block_id": "",
                        "block_type": "transcription",
                        "content": content.strip(),
                        "title": "Последняя транскрипция",
                        "has_transcription": True,
                        "has_summary": False
                    }
                
                if summary_start >= 0:
                    content = '\\n'.join(lines[summary_start:])
                    logger.info(f"✅ Найден саммари в тексте: {len(content)} символов")
                    return {
                        "block_id": "",
                        "block_type": "summary",
                        "content": content.strip(),
                        "title": "Последнее саммари",
                        "has_transcription": False,
                        "has_summary": True
                    }
                
                # Если не нашли метки, берем последние 10000 символов
                last_content = all_text[-10000:].strip()
                logger.info(f"✅ Получен контент через fallback: {len(last_content)} символов")
                return {
                    "block_id": "",
                    "block_type": "fallback",
                    "content": last_content,
                    "title": last_content.split('\\n')[0][:100] if last_content else "",
                    "has_transcription": False,
                    "has_summary": False
                }
        except Exception as e:
            logger.error(f"Ошибка получения контента: {e}")
        
        raise ValueError("Не удалось получить контент последней встречи")
    
    async def get_last_meeting_automatically(self, page_id: Optional[str] = None, headless: bool = True) -> Dict[str, Any]:
        """
        Автоматически получает последний блок встречи через браузер в headless режиме.
        
        Args:
            page_id: ID страницы Notion (если None, используется из настроек)
            headless: Запускать браузер в headless режиме (по умолчанию True)
            
        Returns:
            Словарь с контентом последнего блока:
            {
                "block_id": str,
                "block_type": str,
                "content": str,
                "title": str,
                "has_transcription": bool,
                "has_summary": bool
            }
        """
        if not self.playwright_available:
            raise RuntimeError("Playwright не установлен. Установите: pip install playwright && playwright install webkit")
        
        resolved_page_id = page_id or self.meeting_page_id
        if not resolved_page_id:
            raise ValueError("Не указан page_id и NOTION_MEETING_PAGE_ID не установлен")
        
        # Формируем URL страницы
        clean_id = resolved_page_id.replace('-', '')
        page_url = f"https://www.notion.so/{clean_id}"
        
        logger.info(f"🌐 Автоматически открываем Notion в headless режиме: {page_url}")
        
        from playwright.async_api import async_playwright
        
        async with async_playwright() as playwright:
            browser = None
            browser_context = None
            try:
                # Запускаем браузер в headless режиме
                browser = await playwright.webkit.launch(headless=headless)
                
                # Фаза 2: Работа робота - используем сохраненное состояние сессии
                # Согласно техническому отчету: инъектируем auth.json в контекст браузера
                if self.auth_file.exists():
                    try:
                        browser_context = await browser.new_context(
                            storage_state=str(self.auth_file),
                            viewport={"width": 1920, "height": 1080},
                            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
                        )
                        logger.info("✅ Используется сохраненное состояние сессии (Session Replay)")
                    except Exception as e:
                        logger.warning(f"Не удалось загрузить сохраненное состояние сессии: {e}, используем новый контекст")
                        browser_context = await browser.new_context(
                            viewport={"width": 1920, "height": 1080},
                            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
                        )
                else:
                    # Fallback: используем токен, если сохраненная сессия недоступна
                    browser_context = await browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
                    )
                    
                    # Устанавливаем cookies авторизации, если есть токен
                    if self.auth_token:
                        try:
                            cookies = [
                                {
                                    "name": "token_v2",
                                    "value": self.auth_token,
                                    "domain": ".notion.so",
                                    "path": "/"
                                }
                            ]
                            await browser_context.add_cookies(cookies)
                            logger.info("✅ Установлены cookies авторизации Notion (fallback)")
                        except Exception as e:
                            logger.warning(f"Не удалось установить cookies авторизации: {e}")
                
                page = await browser_context.new_page()
                
                # Переходим на страницу
                logger.info("📄 Загружаем страницу...")
                await page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
                
                # Ждем загрузки контента
                await self._wait_for_content(page)
                
                # Прокручиваем до последнего блока
                await self._scroll_to_last_block(page)
                
                # Извлекаем контент последнего блока
                result = await self._copy_last_block_content(page)
                
                logger.info(f"✅ Автоматически получен контент: {len(result.get('content', ''))} символов")
                return result
                
            except Exception as e:
                logger.error(f"❌ Ошибка при автоматическом получении контента: {e}")
                raise
            finally:
                # Закрываем браузер
                if browser_context:
                    try:
                        await browser_context.close()
                    except Exception as e:
                        logger.debug(f"Ошибка при закрытии browser_context: {e}")
                if browser:
                    try:
                        await browser.close()
                    except Exception as e:
                        logger.debug(f"Ошибка при закрытии browser: {e}")