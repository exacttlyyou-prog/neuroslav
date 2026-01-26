import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

# Путь для сохранения файла авторизации
AUTH_FILE = Path(__file__).parent.parent / "data" / "notion_auth.json"

async def setup_auth():
    print("🚀 Запуск браузера для авторизации...")
    
    async with async_playwright() as p:
        # Запускаем браузер в видимом режиме
        # Пытаемся использовать Chrome, если он установлен, иначе Chromium
        try:
            browser = await p.chromium.launch(headless=False, channel="chrome")
        except Exception:
            print("⚠️ Chrome не найден, используем стандартный Chromium...")
            browser = await p.chromium.launch(headless=False)
            
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print("🔑 Переходим на страницу входа Notion...")
        await page.goto("https://www.notion.so/login")
        
        print("⏳ Пожалуйста, войдите в свой аккаунт Notion в открывшемся окне.")
        print("   Скрипт ждет, пока вы не окажетесь внутри Notion (URL будет содержать 'notion.so').")
        print("   У вас есть 3 минуты.")
        
        try:
            # Ждем, пока пользователь залогинится и URL изменится на внутренний
            # Обычно после логина перекидывает на notion.so/<workspace>
            await page.wait_for_url(lambda url: "login" not in url and "notion.so" in url, timeout=180000)
            
            print("✅ Вход обнаружен! Ждем полной загрузки...")
            # Увеличиваем таймаут ожидания загрузки сети до 60 секунд
            await page.wait_for_load_state("networkidle", timeout=60000)
            
            # Сохраняем состояние
            await context.storage_state(path=AUTH_FILE)
            print(f"💾 Сессия успешно сохранена в: {AUTH_FILE}")
            
        except Exception as e:
            print(f"❌ Ошибка или тайм-аут: {e}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(setup_auth())
