/**
 * Координатор: главный цикл обработки встреч
 * Опрашивает базу данных Notion, находит страницы со статусом "Ready to Process"
 * и запускает цепочку агентов для обработки
 */

import { Client } from '@notionhq/client';
import { config } from 'dotenv';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { MeetingPage, MeetingStatus, Config } from './types.js';
import { logger } from './utils/logger.js';
import { scrapeWithRetry } from './agents/scraper.js';
import { analyzeMeetingContent } from './agents/analyst.js';
import { writeToNotion } from './agents/writer.js';
import { getNotionClient } from './utils/notion.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/**
 * Загрузка конфигурации из переменных окружения
 */
function loadConfig(): Config {
  // Загружаем .env из корня проекта или текущей директории
  const projectRoot = join(__dirname, '../..');
  config({ path: join(projectRoot, '.env') });
  config({ path: join(__dirname, '../.env') });

  const notionToken = process.env.NOTION_TOKEN;
  const openaiApiKey = process.env.OPENAI_API_KEY;
  const notionDbId = process.env.NOTION_DB_ID;
  const notionTasksDbId = process.env.NOTION_TASKS_DB_ID;
  const statusProperty = process.env.NOTION_STATUS_PROPERTY || 'Status';
  const pollInterval = parseInt(process.env.POLL_INTERVAL || '60000', 10);
  const authFilePath = process.env.AUTH_FILE_PATH || join(__dirname, '../../auth.json');

  if (!notionToken) {
    throw new Error('NOTION_TOKEN не установлен в переменных окружения');
  }
  if (!openaiApiKey) {
    throw new Error('OPENAI_API_KEY не установлен в переменных окружения');
  }
  if (!notionDbId) {
    throw new Error('NOTION_DB_ID не установлен в переменных окружения');
  }
  if (!notionTasksDbId) {
    throw new Error('NOTION_TASKS_DB_ID не установлен в переменных окружения');
  }

  return {
    notionToken,
    openaiApiKey,
    notionDbId,
    notionTasksDbId,
    statusProperty,
    pollInterval,
    authFilePath,
  };
}

/**
 * Поиск страниц со статусом "Ready to Process"
 */
async function findPagesToProcess(
  notion: Client,
  dbId: string,
  statusProperty: string
): Promise<MeetingPage[]> {
  try {
    const response = await notion.databases.query({
      database_id: dbId,
      filter: {
        property: statusProperty,
        select: {
          equals: 'Ready to Process',
        },
      },
    });

    const pages: MeetingPage[] = [];

    for (const page of response.results) {
      if ('properties' in page) {
        const titleProperty = Object.values(page.properties).find(
          (prop) => prop.type === 'title'
        );

        const title =
          titleProperty && titleProperty.type === 'title'
            ? titleProperty.title[0]?.plain_text || 'Untitled'
            : 'Untitled';

        pages.push({
          id: page.id,
          url: page.url,
          title,
          status: 'Ready to Process',
        });
      }
    }

    return pages;
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    logger.error(`❌ Ошибка при поиске страниц: ${errorMessage}`);
    return [];
  }
}

/**
 * Обновление статуса страницы
 */
async function updatePageStatus(
  notion: Client,
  pageId: string,
  status: MeetingStatus,
  statusProperty: string
): Promise<void> {
  try {
    await notion.pages.update({
      page_id: pageId,
      properties: {
        [statusProperty]: {
          select: {
            name: status,
          },
        },
      },
    });
    logger.info(`✅ Статус страницы ${pageId} обновлен на "${status}"`);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    logger.error(`❌ Ошибка при обновлении статуса: ${errorMessage}`);
    throw error;
  }
}

/**
 * Обработка одной страницы встречи
 */
async function processPage(
  page: MeetingPage,
  cfg: Config
): Promise<void> {
  const notion = getNotionClient(cfg.notionToken);
  const pageUrl = `https://www.notion.so/${page.id.replace(/-/g, '')}`;

  logger.info(`\n${'='.repeat(60)}`);
  logger.info(`🚀 Начало обработки страницы: ${page.title}`);
  logger.info(`📄 URL: ${pageUrl}`);
  logger.info(`${'='.repeat(60)}\n`);

  try {
    // Шаг 1: Обновляем статус на "Processing"
    await updatePageStatus(notion, page.id, 'Processing', cfg.statusProperty);

    // Шаг 2: Скрапер - извлекаем контент
    logger.info('📥 Шаг 1: Извлечение контента через Scraper...');
    const scraperResult = await scrapeWithRetry(pageUrl, cfg.authFilePath, 3);

    if (!scraperResult.success || !scraperResult.content) {
      throw new Error(`Scraper failed: ${scraperResult.error}`);
    }

    logger.info(`✅ Контент извлечен: ${scraperResult.content.length} символов\n`);

    // Шаг 3: Аналитик - структурируем данные
    logger.info('🤖 Шаг 2: Анализ контента через Analyst...');
    const analystResult = await analyzeMeetingContent(
      scraperResult.content,
      cfg.openaiApiKey
    );

    if (!analystResult.success || !analystResult.data) {
      throw new Error(`Analyst failed: ${analystResult.error}`);
    }

    logger.info(
      `✅ Анализ завершен: ${analystResult.data.actionItems.length} задач, ` +
      `${analystResult.data.keyDecisions.length} решений\n`
    );

    // Шаг 4: Секретарь - записываем в Notion
    logger.info('📝 Шаг 3: Запись данных через Writer...');
    const writerResult = await writeToNotion(
      notion,
      page.id,
      cfg.notionTasksDbId,
      analystResult.data
    );

    if (!writerResult.success) {
      throw new Error(`Writer failed: ${writerResult.error}`);
    }

    logger.info(`✅ Запись завершена: создано ${writerResult.taskIds?.length || 0} задач\n`);

    // Шаг 5: Обновляем статус на "Done"
    await updatePageStatus(notion, page.id, 'Done', cfg.statusProperty);

    logger.info(`✅ Страница "${page.title}" успешно обработана!\n`);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    logger.error(`❌ Ошибка при обработке страницы: ${errorMessage}\n`);

    // Обновляем статус на "Error"
    try {
      await updatePageStatus(notion, page.id, 'Error', cfg.statusProperty);
    } catch (updateError) {
      logger.error(`❌ Не удалось обновить статус на Error: ${updateError}`);
    }
  }
}

/**
 * Главный цикл координатора
 */
export async function runCoordinator(): Promise<void> {
  logger.info('🚀 Запуск координатора мульти-агентной системы...\n');

  const cfg = loadConfig();
  logger.info('✅ Конфигурация загружена');
  logger.info(`   - Meetings DB: ${cfg.notionDbId}`);
  logger.info(`   - Tasks DB: ${cfg.notionTasksDbId}`);
  logger.info(`   - Poll interval: ${cfg.pollInterval}ms\n`);

  const notion = getNotionClient(cfg.notionToken);

  // Главный цикл опроса
  while (true) {
    try {
      logger.info('🔍 Поиск страниц для обработки...');
      const pages = await findPagesToProcess(notion, cfg.notionDbId, cfg.statusProperty);

      if (pages.length === 0) {
        logger.info('⏳ Страниц для обработки не найдено, ожидание...\n');
      } else {
        logger.info(`📋 Найдено ${pages.length} страниц для обработки\n`);

        // Обрабатываем страницы последовательно
        for (const page of pages) {
          await processPage(page, cfg);
        }
      }

      // Ждем перед следующим опросом
      await new Promise((resolve) => setTimeout(resolve, cfg.pollInterval));
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      logger.error(`❌ Критическая ошибка в главном цикле: ${errorMessage}`);
      logger.info('⏳ Повтор через 30 секунд...\n');
      await new Promise((resolve) => setTimeout(resolve, 30000));
    }
  }
}
