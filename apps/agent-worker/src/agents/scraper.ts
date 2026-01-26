/**
 * Агент-Скрапер: извлекает контент из AI Meeting Notes через Playwright
 * Использует Smart Scroll для виртуализированного контента Notion
 */

import { chromium, Browser, BrowserContext, Page } from 'playwright';
import { existsSync, readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { ScraperResult } from '../types.js';
import { logger } from '../utils/logger.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/**
 * Умная прокрутка страницы для загрузки виртуализированного контента Notion
 */
async function smartScroll(
  page: Page,
  maxScrolls: number = 20,
  scrollStep: number = 800,
  waitTime: number = 500
): Promise<void> {
  let previousHeight = 0;
  let scrollCount = 0;

  while (scrollCount < maxScrolls) {
    const currentHeight = await page.evaluate(() => {
      return document.documentElement.scrollHeight;
    });

    if (currentHeight === previousHeight) {
      break;
    }

    previousHeight = currentHeight;

    await page.evaluate((step) => {
      window.scrollBy(0, step);
    }, scrollStep);

    await page.waitForTimeout(waitTime);
    scrollCount++;
  }
}

/**
 * Извлечение контента AI Summary через Playwright
 */
export async function scrapeMeetingContent(
  pageUrl: string,
  authFilePath?: string
): Promise<ScraperResult> {
  logger.info(`🌐 Запуск браузера для извлечения данных: ${pageUrl}`);

  const browser = await chromium.launch({
    headless: true,
  });

  try {
    let context: BrowserContext | null = null;

    // Пробуем загрузить сохраненное состояние сессии
    const authFile = authFilePath || join(__dirname, '../../auth.json');
    
    if (existsSync(authFile)) {
      logger.info('📁 Использование сохраненного состояния сессии...');
      try {
        const storageState = JSON.parse(readFileSync(authFile, 'utf-8'));
        context = await browser.newContext({
          storageState,
          viewport: { width: 1920, height: 1080 },
        });
        logger.info('✅ Состояние сессии загружено');
      } catch (error) {
        logger.warn(`⚠️  Не удалось загрузить auth.json: ${error}`);
      }
    }

    // Если не удалось загрузить сессию, создаем новый контекст
    if (!context) {
      logger.warn('⚠️  Создаем новый контекст без сохраненной сессии');
      context = await browser.newContext({
        viewport: { width: 1920, height: 1080 },
      });
    }

    const page = await context.newPage();

    logger.info(`📄 Переход на страницу: ${pageUrl}`);
    await page.goto(pageUrl, {
      waitUntil: 'networkidle',
      timeout: 30000,
    });

    // Ждем появления блоков
    logger.info('⏳ Ожидание загрузки страницы...');
    try {
      await page.waitForSelector('div[data-block-id]', { timeout: 10000 });
    } catch (e) {
      logger.warn('⚠️  Блоки не найдены сразу, продолжаем...');
    }

    // Умная прокрутка для загрузки виртуализированного контента
    logger.info('📜 Прокрутка страницы для загрузки контента...');
    await smartScroll(page, 20, 800, 500);

    // Дополнительное ожидание
    await page.waitForTimeout(2000);

    // Ищем блоки с текстом "AI Summary" или "Summary"
    logger.info('🔍 Поиск блоков AI Summary...');

    let summaryText: string | null = null;

    // Стратегия 1: Поиск по тексту
    try {
      const summaryElement = page.locator('div')
        .filter({ hasText: /AI Summary|Summary|Саммари|Резюме/i })
        .first();

      if (await summaryElement.count() > 0) {
        const blockId = await summaryElement.getAttribute('data-block-id');
        
        if (blockId) {
          const blockElement = page.locator(`div[data-block-id="${blockId}"]`).first();
          summaryText = await blockElement.textContent();
        } else {
          summaryText = await summaryElement.textContent();
        }
      }
    } catch (e) {
      logger.warn('⚠️  Поиск по тексту не дал результатов');
    }

    // Стратегия 2: Поиск по data-block-id
    if (!summaryText) {
      try {
        const allBlocks = await page.locator('div[data-block-id]').all();
        
        for (const block of allBlocks) {
          const text = await block.textContent();
          if (text && /AI Summary|Summary|Саммари|Резюме/i.test(text)) {
            summaryText = text;
            
            // Пытаемся получить больше контента из соседних блоков
            const nextBlocks = await block.locator('..').locator('div[data-block-id]').all();
            const additionalText: string[] = [];
            
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
        logger.warn('⚠️  Поиск по data-block-id не дал результатов');
      }
    }

    // Стратегия 3: Fallback - извлекаем весь контент
    if (!summaryText) {
      logger.warn('⚠️  Точный поиск не дал результатов, извлекаем весь контент страницы...');
      try {
        const allText = await page.locator('div[data-block-id]').allTextContents();
        summaryText = allText.join('\n\n');
      } catch (e) {
        logger.error('❌ Не удалось извлечь текст');
      }
    }

    await browser.close();

    if (summaryText && summaryText.trim()) {
      logger.info(`✅ Данные успешно извлечены: ${summaryText.length} символов`);
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
    const errorMessage = error instanceof Error ? error.message : String(error);
    logger.error(`❌ Ошибка при извлечении данных: ${errorMessage}`);
    return {
      success: false,
      error: `Ошибка при извлечении данных: ${errorMessage}`,
    };
  }
}

/**
 * Retry wrapper для Scraper с экспоненциальной задержкой
 */
export async function scrapeWithRetry(
  pageUrl: string,
  authFilePath?: string,
  maxRetries: number = 3
): Promise<ScraperResult> {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    logger.info(`🔄 Попытка ${attempt}/${maxRetries} извлечения контента...`);
    
    const result = await scrapeMeetingContent(pageUrl, authFilePath);
    
    if (result.success) {
      return result;
    }

    if (attempt < maxRetries) {
      const delay = Math.pow(2, attempt) * 1000; // Экспоненциальная задержка
      logger.warn(`⚠️  Попытка ${attempt} не удалась, повтор через ${delay}мс...`);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }

  return {
    success: false,
    error: `Не удалось извлечь контент после ${maxRetries} попыток`,
  };
}
