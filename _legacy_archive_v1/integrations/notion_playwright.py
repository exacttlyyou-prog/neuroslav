"""
Получение контента Notion через браузер (Playwright).
Используется для получения transcription блоков, которые недоступны через API.
"""
import asyncio
from typing import Optional
from loguru import logger
from pathlib import Path
import os


class NotionPlaywright:
    """Получение контента Notion через браузер с помощью Playwright."""
    
    def __init__(self):
        # Путь к профилю Chrome (где пользователь уже залогинен)
        # macOS: ~/Library/Application Support/Google/Chrome
        # Пробуем разные возможные пути
        home = Path.home()
        possible_paths = [
            home / "Library/Application Support/Google/Chrome",
            home / "Library/Application Support/Chromium",
            home / ".config/google-chrome",
        ]
        
        self.chrome_user_data = None
        for path in possible_paths:
            if path.exists():
                self.chrome_user_data = path
                logger.debug(f"Найден профиль Chrome: {path}")
                break
        
        if not self.chrome_user_data:
            logger.warning("Профиль Chrome не найден, будет использован новый профиль (потребуется авторизация)")
        
        # Проверяем наличие Playwright
        try:
            from playwright.async_api import async_playwright
            self.playwright_available = True
        except ImportError:
            logger.warning("Playwright не установлен. Установите: pip install playwright && playwright install chromium")
            self.playwright_available = False
    
    async def get_page_content(self, page_url: str, timeout: int = 60000) -> Optional[str]:
        """
        Получает контент страницы Notion через браузер.
        
        Args:
            page_url: Полный URL страницы Notion
            timeout: Таймаут в миллисекундах
            
        Returns:
            Текст контента страницы или None при ошибке
        """
        if not self.playwright_available:
            logger.debug("Playwright недоступен")
            return None
        
        try:
            from playwright.async_api import async_playwright
            
            logger.info(f"🌐 Открываем страницу в браузере: {page_url}")
            
            async with async_playwright() as p:
                # Запускаем браузер
                if self.chrome_user_data and self.chrome_user_data.exists():
                    # Используем сохраненный профиль (где уже залогинен)
                    # Если это уже профиль (Default, Profile 1), используем его напрямую
                    # Если это корневая директория Chrome, используем Default
                    if self.chrome_user_data.name in ["Default", "Profile 1"]:
                        profile_to_use = self.chrome_user_data
                    else:
                        # Это корневая директория, ищем Default профиль
                        default_profile = self.chrome_user_data / "Default"
                        profile_to_use = default_profile if default_profile.exists() else self.chrome_user_data
                    
                    logger.debug(f"Используем профиль: {profile_to_use}")
                    
                    # Пробуем запустить с persistent context
                    # Если не работает, используем обычный launch с cookies
                    try:
                        browser_context = await p.chromium.launch_persistent_context(
                            user_data_dir=str(profile_to_use),
                            headless=True,  # Невидимый режим
                            viewport={"width": 1920, "height": 1080},
                            timeout=timeout,
                            # Дополнительные опции для работы с Notion
                            args=[
                                '--disable-blink-features=AutomationControlled',
                                '--disable-dev-shm-usage',
                                '--no-sandbox',
                            ],
                            # Используем тот же user agent, что и в браузере
                            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                        )
                    except Exception as persistent_error:
                        logger.warning(f"Не удалось запустить persistent context: {persistent_error}")
                        # Fallback: обычный браузер
                        browser = await p.chromium.launch(headless=True)
                        browser_context = await browser.new_context(
                            viewport={"width": 1920, "height": 1080},
                            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                        )
                        use_persistent = False
                    use_persistent = True
                else:
                    # Запускаем новый браузер (потребуется авторизация)
                    browser = await p.chromium.launch(headless=True)
                    browser_context = await browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                    use_persistent = False
                
                try:
                    page = await browser_context.new_page()
                    
                    # Переходим на страницу
                    # Используем "domcontentloaded" вместо "networkidle" для более быстрой загрузки
                    await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout)
                    logger.debug("Страница загружена, ждем загрузки контента...")
                    
                    # Проверяем, не попали ли на страницу входа
                    page_text = await page.inner_text("body")
                    if "Sign in" in page_text or "Continue with" in page_text or "Log in" in page_text:
                        logger.warning("Обнаружена страница входа - профиль Chrome не содержит авторизацию Notion")
                        logger.info("💡 Попробуйте открыть Notion в браузере и авторизоваться, затем запустите снова")
                        return None
                    
                    # Ждем загрузки контента (особенно для transcription блоков)
                    # Пробуем разные селекторы для контента Notion
                    try:
                        # Ждем появления контента страницы Notion
                        await page.wait_for_selector(
                            ".notion-page-content, [data-content-editable-root], .notion-page-view, .notion-page-body, [class*='notion-page']", 
                            timeout=15000
                        )
                        logger.debug("Контент страницы найден")
                    except Exception:
                        logger.debug("Селектор контента не найден, продолжаем...")
                    
                    # Дополнительное ожидание для динамической загрузки transcription блоков
                    # Notion загружает контент динамически через JavaScript
                    await asyncio.sleep(8)
                    
                    # Пробуем прокрутить страницу вниз, чтобы загрузить весь контент
                    try:
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(2)
                        await page.evaluate("window.scrollTo(0, 0)")
                        await asyncio.sleep(2)
                    except Exception:
                        pass
                    
                    # Пробуем разные способы получения контента
                    content = None
                    
                    # Метод 1: Получаем весь текст страницы
                    try:
                        content = await page.inner_text("body")
                        
                        # Проверяем, не попали ли на страницу входа
                        if content and ("Sign in" in content or "Continue with" in content or "Log in" in content):
                            logger.warning("Обнаружена страница входа - профиль Chrome не содержит авторизацию Notion")
                            logger.info("💡 Попробуйте открыть Notion в браузере и авторизоваться, затем запустите снова")
                            return None
                        
                        if content and len(content.strip()) > 100:
                            logger.info(f"✅ Получен контент через body: {len(content)} символов")
                    except Exception as e:
                        logger.debug(f"Ошибка получения через body: {e}")
                    
                    # Метод 2: Используем JavaScript для получения данных из Notion
                    transcription_content = None
                    try:
                        # Notion хранит данные в window.__INITIAL_STATE__ или других глобальных переменных
                        js_code = """
                        () => {
                            // Пробуем получить данные из разных источников
                            let data = null;
                            
                            // Вариант 1: window.__INITIAL_STATE__
                            if (window.__INITIAL_STATE__) {
                                data = window.__INITIAL_STATE__;
                            }
                            
                            // Вариант 2: Ищем все блоки с transcription
                            let transcriptionBlocks = [];
                            document.querySelectorAll('[data-block-type="transcription"], [class*="transcription"], [aria-label*="transcription"]').forEach(block => {
                                let text = block.innerText || block.textContent;
                                if (text && text.length > 100) {
                                    transcriptionBlocks.push(text.trim());
                                }
                            });
                            
                            // Вариант 3: Ищем текст с ключевыми словами
                            let allText = document.body.innerText || document.body.textContent || '';
                            
                            return {
                                initialState: data ? 'found' : 'not found',
                                transcriptionBlocks: transcriptionBlocks,
                                allTextLength: allText.length,
                                hasSummary: allText.toLowerCase().includes('summary') || allText.toLowerCase().includes('резюме'),
                                hasTranscript: allText.toLowerCase().includes('transcript') || allText.toLowerCase().includes('транскрипт')
                            };
                        }
                        """
                        js_result = await page.evaluate(js_code)
                        logger.debug(f"JavaScript результат: {js_result}")
                        
                        if js_result.get('transcriptionBlocks') and len(js_result['transcriptionBlocks']) > 0:
                            transcription_content = "\n\n".join(js_result['transcriptionBlocks'])
                            logger.info(f"✅ Найден transcription через JavaScript: {len(transcription_content)} символов")
                        
                    except Exception as e:
                        logger.debug(f"Ошибка JavaScript поиска: {e}")
                    
                    # Метод 3: Ищем transcription блоки по специфичным селекторам
                    if not transcription_content:
                        try:
                            # Ищем блоки с transcription/meeting-notes
                            transcription_selectors = [
                                '[data-block-type="transcription"]',
                                '[data-block-type="meeting-notes"]',
                                '.notion-transcription-block',
                                '[class*="transcription"]',
                                '[class*="meeting-notes"]',
                                '[aria-label*="transcription"]',
                                '[aria-label*="meeting"]',
                            ]
                            
                            for selector in transcription_selectors:
                                try:
                                    elements = await page.query_selector_all(selector)
                                    if elements:
                                        logger.debug(f"Найдено элементов с селектором {selector}: {len(elements)}")
                                        texts = []
                                        for elem in elements:
                                            text = await elem.inner_text()
                                            if text and len(text.strip()) > 100:
                                                texts.append(text.strip())
                                        
                                        if texts:
                                            transcription_content = "\n\n".join(texts)
                                            logger.info(f"✅ Найден transcription контент через селектор {selector}: {len(transcription_content)} символов")
                                            break
                                except Exception:
                                    continue
                        except Exception as e:
                            logger.debug(f"Ошибка поиска transcription блоков: {e}")
                    
                    # Если нашли transcription, используем его
                    if transcription_content:
                        content = transcription_content
                    
                    # Метод 3: Получаем HTML и парсим для поиска transcription
                    if not transcription_content:
                        try:
                            html = await page.content()
                            # Ищем meeting-notes/transcription в HTML разными способами
                            import re
                            
                            # Паттерн 1: Ищем блоки с transcription в атрибутах
                            transcription_patterns = [
                                r'<div[^>]*data-block-type=["\']transcription["\'][^>]*>(.*?)</div>',
                                r'<div[^>]*class=["\'][^"\']*transcription[^"\']*["\'][^>]*>(.*?)</div>',
                                r'<div[^>]*aria-label=["\'][^"\']*transcription[^"\']*["\'][^>]*>(.*?)</div>',
                                r'<div[^>]*data-block-id[^>]*>(.*?)(?:<div[^>]*data-block-id|</body>)',  # Все блоки
                            ]
                            
                            for pattern in transcription_patterns:
                                matches = re.finditer(pattern, html, re.DOTALL | re.IGNORECASE)
                                for match in matches:
                                    try:
                                        from bs4 import BeautifulSoup
                                        soup = BeautifulSoup(match.group(1), 'html.parser')
                                        text = soup.get_text(separator=' ', strip=True)
                                        # Проверяем, что это действительно transcription (содержит ключевые слова)
                                        if text and len(text.strip()) > 200:
                                            lower_text = text.lower()
                                            if any(kw in lower_text for kw in ['summary', 'transcript', 'meeting', 'встреча', 'резюме', 'саммари']):
                                                transcription_content = text
                                                logger.info(f"✅ Найден transcription в HTML: {len(transcription_content)} символов")
                                                break
                                    except Exception:
                                        continue
                                
                                if transcription_content:
                                    break
                            
                            if transcription_content:
                                content = transcription_content
                        except Exception as e:
                            logger.debug(f"Ошибка парсинга HTML: {e}")
                    
                    return content
                    
                finally:
                    # Закрываем браузер правильно
                    try:
                        if use_persistent:
                            await browser_context.close()
                        else:
                            await browser_context.close()
                            if 'browser' in locals():
                                await browser.close()
                    except Exception as close_error:
                        logger.debug(f"Ошибка при закрытии браузера: {close_error}")
                    
        except Exception as e:
            logger.error(f"Ошибка при получении контента через Playwright: {e}")
            return None
    
    async def get_page_by_id(self, page_id: str) -> Optional[str]:
        """
        Получает контент страницы по ID через браузер.
        
        Args:
            page_id: ID страницы Notion (с дефисами или без)
            
        Returns:
            Текст контента страницы или None при ошибке
        """
        # Формируем URL
        clean_id = page_id.replace('-', '')
        page_url = f"https://www.notion.so/{clean_id}"
        
        return await self.get_page_content(page_url)
