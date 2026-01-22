#!/usr/bin/env node
/**
 * Модуль извлечения данных из Notion через Playwright (fallback метод).
 * Пробует автоматическую авторизацию через токен, затем использует сохраненное состояние сессии.
 */
import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { existsSync } from 'fs';
import { config } from 'dotenv';

// Загружаем переменные окружения (сначала из текущей директории, затем из корня проекта)
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const projectRoot = join(__dirname, '..', '..');

if (existsSync(join(__dirname, '.env'))) {
  config({ path: join(__dirname, '.env') });
} else if (existsSync(join(projectRoot, '.env'))) {
  config({ path: join(projectRoot, '.env') });
} else {
  config(); // Пробуем стандартные пути
}

// __filename и __dirname уже определены выше
const AUTH_FILE = join(__dirname, 'notion-auth.json');

/**
 * Умная прокрутка страницы для загрузки виртуализированного контента.
 * @param {import('playwright').Page} page - Страница Playwright
 * @param {number} maxScrolls - Максимальное количество прокруток
 * @param {number} scrollStep - Шаг прокрутки в пикселях
 * @param {number} waitTime - Время ожидания после каждой прокрутки (мс)
 */
async function smartScroll(page, maxScrolls = 20, scrollStep = 800, waitTime = 500) {
  let previousHeight = 0;
  let scrollCount = 0;

  while (scrollCount < maxScrolls) {
    // Получаем текущую высоту страницы
    const currentHeight = await page.evaluate(() => {
      return document.documentElement.scrollHeight;
    });

    // Если высота не изменилась, значит мы достигли конца
    if (currentHeight === previousHeight) {
      break;
    }

    previousHeight = currentHeight;

    // Прокручиваем вниз
    await page.evaluate((step) => {
      window.scrollBy(0, step);
    }, scrollStep);

    // Ждем загрузки контента
    await page.waitForTimeout(waitTime);

    scrollCount++;
  }
}

/**
 * Извлечение текста из блоков AI Meeting Notes через Playwright.
 * @param {string} pageId - ID страницы Notion
 * @returns {Promise<{success: boolean, content?: string, error?: string}>}
 */
export async function extractViaPlaywright(pageId) {
  console.log('🌐 Запуск браузера для извлечения данных...');

  const browser = await chromium.launch({
    headless: true, // Headless режим для автоматизации
  });

  try {
    const notionToken = process.env.NOTION_TOKEN;
    
    // Пробуем создать контекст с автоматической авторизацией
    let context;
    
    if (notionToken) {
      // Метод 1: Пробуем использовать токен напрямую через cookies
      console.log('🔑 Попытка автоматической авторизации через токен...');
      context = await browser.newContext({
        viewport: { width: 1920, height: 1080 },
      });

      // Пытаемся установить cookies авторизации
      // Примечание: Notion API токены (ntn_...) могут не работать напрямую в браузере,
      // но пробуем установить как token_v2
      try {
        await context.addCookies([
          {
            name: 'token_v2',
            value: notionToken,
            domain: '.notion.so',
            path: '/',
          },
        ]);
        console.log('✅ Cookies авторизации установлены');
      } catch (cookieError) {
        console.log('⚠️  Не удалось установить cookies через токен, пробуем сохраненную сессию...');
        await context.close();
        context = null;
      }
    }

    // Метод 2: Если токен не сработал, используем сохраненное состояние сессии
    if (!context && existsSync(AUTH_FILE)) {
      console.log('📁 Использование сохраненного состояния сессии...');
      context = await browser.newContext({
        storageState: AUTH_FILE,
        viewport: { width: 1920, height: 1080 },
      });
    } else if (!context) {
      // Если нет ни токена, ни сохраненной сессии
      await browser.close();
      return {
        success: false,
        error: `Не удалось авторизоваться. Установите NOTION_TOKEN в .env или запустите setup-auth.js для создания сессии.`,
      };
    }

    const page = await context.newPage();

    // Формируем URL страницы
    const cleanId = pageId.replace(/-/g, '');
    const pageUrl = `https://www.notion.so/${cleanId}`;

    console.log(`📄 Переход на страницу: ${pageUrl}`);

    // Переходим на страницу
    await page.goto(pageUrl, {
      waitUntil: 'networkidle',
      timeout: 30000,
    });

    // Ждем появления заголовка страницы (индикатор загрузки)
    console.log('⏳ Ожидание загрузки страницы...');
    try {
      // Пытаемся найти заголовок страницы (разные возможные селекторы)
      await page.waitForSelector('div[data-block-id]', { timeout: 10000 });
    } catch (e) {
      console.log('⚠️  Заголовок не найден, продолжаем...');
    }

    // Умная прокрутка для загрузки виртуализированного контента
    console.log('📜 Прокрутка страницы для загрузки контента...');
    await smartScroll(page, 20, 800, 500);

    // Дополнительное ожидание для завершения загрузки
    await page.waitForTimeout(2000);

    // Ищем блоки с текстом "AI Summary" или "Summary"
    console.log('🔍 Поиск блоков AI Summary...');

    let summaryText = null;

    // Стратегия 1: Поиск по тексту
    try {
      const summaryElement = await page.locator('div')
        .filter({ hasText: /AI Summary|Summary|Саммари|Резюме/i })
        .first();

      if (await summaryElement.count() > 0) {
        // Пытаемся найти родительский блок и извлечь весь контент
        const blockId = await summaryElement.getAttribute('data-block-id');
        
        if (blockId) {
          // Ищем весь блок с этим ID и извлекаем текст
          const blockElement = page.locator(`div[data-block-id="${blockId}"]`).first();
          summaryText = await blockElement.textContent();
        } else {
          // Если нет block-id, просто берем текст элемента
          summaryText = await summaryElement.textContent();
        }
      }
    } catch (e) {
      console.log('⚠️  Поиск по тексту не дал результатов, пробуем другие методы...');
    }

    // Стратегия 2: Поиск по data-block-id (более надежный метод)
    if (!summaryText) {
      try {
        const allBlocks = await page.locator('div[data-block-id]').all();
        
        for (const block of allBlocks) {
          const text = await block.textContent();
          if (text && /AI Summary|Summary|Саммари|Резюме/i.test(text)) {
            // Нашли блок, извлекаем весь контент из этого блока и следующих
            summaryText = text;
            
            // Пытаемся получить больше контента из соседних блоков
            const nextBlocks = await block.locator('..').locator('div[data-block-id]').all();
            const additionalText = [];
            
            for (let i = 0; i < Math.min(10, nextBlocks.length); i++) {
              const nextText = await nextBlocks[i].textContent();
              if (nextText && nextText.trim()) {
                additionalText.push(nextText.trim());
              }
            }
            
            if (additionalText.length > 0) {
              summaryText = [summaryText, ...additionalText].join('\n\n');
            }
            
            break;
          }
        }
      } catch (e) {
        console.log('⚠️  Поиск по data-block-id не дал результатов');
      }
    }

    // Стратегия 3: Поиск всех блоков и извлечение всего текста (fallback)
    if (!summaryText) {
      console.log('⚠️  Точный поиск не дал результатов, извлекаем весь контент страницы...');
      try {
        const allText = await page.locator('div[data-block-id]').allTextContents();
        summaryText = allText.join('\n\n');
      } catch (e) {
        console.log('❌ Не удалось извлечь текст');
      }
    }

    await browser.close();

    if (summaryText && summaryText.trim()) {
      console.log('✅ Данные успешно извлечены');
      return {
        success: true,
        content: summaryText.trim(),
      };
    } else {
      return {
        success: false,
        error: 'Не удалось найти контент AI Summary на странице',
      };
    }

  } catch (error) {
    await browser.close();
    return {
      success: false,
      error: `Ошибка при извлечении данных: ${error.message}`,
    };
  }
}

// Если скрипт запущен напрямую (для тестирования)
if (import.meta.url === `file://${process.argv[1]}`) {
  const pageId = process.argv[2];
  
  if (!pageId) {
    console.error('❌ Укажите page_id как аргумент: node extract.js <page_id>');
    process.exit(1);
  }

  extractViaPlaywright(pageId)
    .then((result) => {
      if (result.success) {
        console.log('\n📄 Извлеченный контент:');
        console.log('=' .repeat(60));
        console.log(result.content);
        console.log('=' .repeat(60));
      } else {
        console.error('\n❌ Ошибка:', result.error);
        process.exit(1);
      }
    })
    .catch((error) => {
      console.error('❌ Критическая ошибка:', error);
      process.exit(1);
    });
}
