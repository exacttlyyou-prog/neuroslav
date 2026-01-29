"""
Скрипт для ручной настройки аутентификации Notion через Playwright.
Реализует паттерн "Session Replay" согласно техническому отчету.

Использование:
    python -m app.scripts.setup_notion_auth

После успешного входа в Notion, состояние сессии сохраняется в auth.json
и может использоваться для автоматического доступа без повторного ввода пароля.
"""
import asyncio
import json
from pathlib import Path
from loguru import logger

try:
    from playwright.async_api import async_playwright
except ImportError:
    logger.error("Playwright не установлен. Установите: pip install playwright && playwright install webkit")
    exit(1)


async def setup_notion_auth():
    """
    Фаза 1: Ручная генерация слепка сессии (выполняется человеком один раз).
    
    Запускает браузер в видимом режиме, переходит на страницу входа Notion,
    ждет пока пользователь вручную войдет, затем сохраняет состояние сессии.
    """
    auth_file = Path(__file__).parent.parent.parent / "data" / "notion_auth.json"
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 60)
    logger.info("🔐 Настройка аутентификации Notion через Playwright")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Инструкция:")
    logger.info("1. Браузер откроется в видимом режиме")
    logger.info("2. Перейдите на страницу входа Notion")
    logger.info("3. Войдите вручную (введите пароль, пройдите 2FA, если требуется)")
    logger.info("4. После успешного входа в рабочее пространство, скрипт автоматически сохранит сессию")
    logger.info("")
    logger.info("⏳ Запускаем браузер...")
    
    async with async_playwright() as playwright:
        # Запускаем браузер в видимом режиме (headless: false)
        browser = await playwright.webkit.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
        )
        
        page = await context.new_page()
        
        try:
            # Переходим на страницу входа
            logger.info("📄 Переходим на страницу входа Notion...")
            await page.goto("https://www.notion.so/login", wait_until="domcontentloaded", timeout=30000)
            
            logger.info("")
            logger.info("=" * 60)
            logger.info("👤 ВХОД В NOTION")
            logger.info("=" * 60)
            logger.info("Пожалуйста, войдите в Notion в открывшемся браузере:")
            logger.info("- Введите email и пароль")
            logger.info("- Пройдите 2FA, если требуется")
            logger.info("- Нажмите 'Continue with Google', если используете SSO")
            logger.info("")
            logger.info("⏳ Ожидаем успешного входа...")
            logger.info("(Скрипт будет ждать, пока URL не изменится на notion.so/my-workspace...)")
            logger.info("")
            
            # Ждем, пока URL не изменится на рабочее пространство
            # Это индикатор успешного входа
            max_wait_time = 300  # Максимум 5 минут
            wait_interval = 2  # Проверяем каждые 2 секунды
            
            for attempt in range(max_wait_time // wait_interval):
                current_url = page.url
                
                # Проверяем, что мы в рабочем пространстве
                if "notion.so" in current_url and ("/my-workspace" in current_url or current_url.count("/") >= 2):
                    # Проверяем, что это не страница входа
                    if "/login" not in current_url and "/signin" not in current_url:
                        logger.info(f"✅ Успешный вход обнаружен! URL: {current_url}")
                        break
                
                await asyncio.sleep(wait_interval)
                
                if attempt % 15 == 0 and attempt > 0:  # Каждые 30 секунд
                    logger.info(f"⏳ Ожидание входа... (прошло {attempt * wait_interval} секунд)")
            else:
                logger.error("❌ Превышено время ожидания входа. Попробуйте запустить скрипт снова.")
                await browser.close()
                return False
            
            # Дополнительное ожидание для полной загрузки рабочего пространства
            logger.info("⏳ Ожидаем полной загрузки рабочего пространства...")
            await asyncio.sleep(3)
            
            # Сохраняем состояние сессии
            logger.info("💾 Сохраняем состояние сессии...")
            storage_state = await context.storage_state()
            
            with open(auth_file, "w", encoding="utf-8") as f:
                json.dump(storage_state, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ Состояние сессии сохранено в: {auth_file}")
            logger.info("")
            logger.info("=" * 60)
            logger.info("✅ НАСТРОЙКА ЗАВЕРШЕНА")
            logger.info("=" * 60)
            logger.info("Теперь вы можете использовать сохраненную сессию для автоматического доступа к Notion.")
            logger.info("Файл auth.json содержит валидные токены сессии (token_v2), которые живут длительное время.")
            logger.info("")
            logger.info("⚠️  ВАЖНО: Добавьте auth.json в .gitignore, чтобы не коммитить токены!")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при настройке аутентификации: {e}", exc_info=True)
            return False
        finally:
            # Закрываем браузер
            await browser.close()
            logger.info("🔒 Браузер закрыт")


if __name__ == "__main__":
    success = asyncio.run(setup_notion_auth())
    exit(0 if success else 1)
