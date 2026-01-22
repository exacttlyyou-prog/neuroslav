#!/usr/bin/env node
/**
 * Главная точка входа для извлечения данных из блоков AI Meeting Notes в Notion.
 * Реализует гибридный подход:
 * 1. Метод 1: Попытка извлечения через официальный Notion API
 * 2. Метод 2: Fallback на Playwright, если API не дал результатов
 */
import { Client } from '@notionhq/client';
import { config } from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { existsSync } from 'fs';
import { extractViaPlaywright } from './extract.js';

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

/**
 * Рекурсивное получение всех блоков страницы через Notion API.
 * @param {Client} notion - Клиент Notion API
 * @param {string} blockId - ID блока для получения дочерних элементов
 * @param {Array} allBlocks - Массив для накопления всех блоков
 */
async function getAllBlocksRecursive(notion, blockId, allBlocks = []) {
  try {
    const response = await notion.blocks.children.list({
      block_id: blockId,
      page_size: 100,
    });

    for (const block of response.results) {
      allBlocks.push(block);

      // Если блок имеет дочерние элементы, рекурсивно получаем их
      if (block.has_children) {
        await getAllBlocksRecursive(notion, block.id, allBlocks);
      }
    }

    // Обработка пагинации
    if (response.has_more && response.next_cursor) {
      let nextCursor = response.next_cursor;
      
      while (nextCursor) {
        const nextResponse = await notion.blocks.children.list({
          block_id: blockId,
          page_size: 100,
          start_cursor: nextCursor,
        });

        for (const block of nextResponse.results) {
          allBlocks.push(block);
          if (block.has_children) {
            await getAllBlocksRecursive(notion, block.id, allBlocks);
          }
        }

        nextCursor = nextResponse.has_more ? nextResponse.next_cursor : null;
      }
    }

    return allBlocks;
  } catch (error) {
    console.error('Ошибка при получении блоков:', error.message);
    return allBlocks;
  }
}

/**
 * Извлечение текста из блока Notion.
 * @param {Object} block - Блок Notion
 * @returns {string} - Извлеченный текст
 */
function extractTextFromBlock(block) {
  const texts = [];

  // Обработка разных типов блоков
  if (block.type === 'paragraph' && block.paragraph?.rich_text) {
    for (const text of block.paragraph.rich_text) {
      if (text.plain_text) {
        texts.push(text.plain_text);
      }
    }
  } else if (block.type === 'heading_1' && block.heading_1?.rich_text) {
    for (const text of block.heading_1.rich_text) {
      if (text.plain_text) {
        texts.push(text.plain_text);
      }
    }
  } else if (block.type === 'heading_2' && block.heading_2?.rich_text) {
    for (const text of block.heading_2.rich_text) {
      if (text.plain_text) {
        texts.push(text.plain_text);
      }
    }
  } else if (block.type === 'heading_3' && block.heading_3?.rich_text) {
    for (const text of block.heading_3.rich_text) {
      if (text.plain_text) {
        texts.push(text.plain_text);
      }
    }
  } else if (block.type === 'bulleted_list_item' && block.bulleted_list_item?.rich_text) {
    for (const text of block.bulleted_list_item.rich_text) {
      if (text.plain_text) {
        texts.push(text.plain_text);
      }
    }
  } else if (block.type === 'numbered_list_item' && block.numbered_list_item?.rich_text) {
    for (const text of block.numbered_list_item.rich_text) {
      if (text.plain_text) {
        texts.push(text.plain_text);
      }
    }
  } else if (block.type === 'to_do' && block.to_do?.rich_text) {
    for (const text of block.to_do.rich_text) {
      if (text.plain_text) {
        texts.push(text.plain_text);
      }
    }
  } else if (block.type === 'toggle' && block.toggle?.rich_text) {
    for (const text of block.toggle.rich_text) {
      if (text.plain_text) {
        texts.push(text.plain_text);
      }
    }
  } else if (block.type === 'callout' && block.callout?.rich_text) {
    for (const text of block.callout.rich_text) {
      if (text.plain_text) {
        texts.push(text.plain_text);
      }
    }
  } else if (block.type === 'quote' && block.quote?.rich_text) {
    for (const text of block.quote.rich_text) {
      if (text.plain_text) {
        texts.push(text.plain_text);
      }
    }
  } else if (block.type === 'code' && block.code?.rich_text) {
    for (const text of block.code.rich_text) {
      if (text.plain_text) {
        texts.push(text.plain_text);
      }
    }
  } else if (block.type === 'unsupported') {
    // Пытаемся извлечь текст из unsupported блоков
    // Иногда они содержат plain_text в других свойствах
    if (block.unsupported) {
      const blockStr = JSON.stringify(block.unsupported);
      // Ищем plain_text в строковом представлении
      const plainTextMatch = blockStr.match(/"plain_text"\s*:\s*"([^"]+)"/g);
      if (plainTextMatch) {
        for (const match of plainTextMatch) {
          const text = match.match(/"plain_text"\s*:\s*"([^"]+)"/)?.[1];
          if (text) {
            texts.push(text);
          }
        }
      }
    }
  }

  return texts.join(' ');
}

/**
 * Метод 1: Извлечение через Notion API.
 * @param {string} pageId - ID страницы Notion
 * @returns {Promise<{success: boolean, content?: string, error?: string}>}
 */
async function extractViaAPI(pageId) {
  const notionToken = process.env.NOTION_TOKEN;

  if (!notionToken) {
    return {
      success: false,
      error: 'NOTION_TOKEN не установлен в переменных окружения',
    };
  }

  console.log('🔌 Попытка извлечения через Notion API...');

  try {
    const notion = new Client({
      auth: notionToken,
    });

    // Получаем все блоки страницы рекурсивно
    console.log('📥 Получение блоков страницы...');
    const allBlocks = await getAllBlocksRecursive(notion, pageId);

    if (allBlocks.length === 0) {
      return {
        success: false,
        error: 'Не удалось получить блоки страницы через API',
      };
    }

    console.log(`✅ Получено ${allBlocks.length} блоков`);

    // Извлекаем текст из всех блоков
    const allText = [];
    let foundSummary = false;

    for (const block of allBlocks) {
      const blockText = extractTextFromBlock(block);
      
      if (blockText) {
        allText.push(blockText);

        // Проверяем, содержит ли блок текст "Summary" или "AI Summary"
        if (/AI Summary|Summary|Саммари|Резюме/i.test(blockText)) {
          foundSummary = true;
        }
      }
    }

    const fullText = allText.join('\n\n');

    // Если нашли секцию Summary или получили достаточно текста
    if (foundSummary || fullText.length > 100) {
      console.log('✅ Данные успешно извлечены через API');
      
      // Если нашли Summary, пытаемся извлечь только эту секцию
      if (foundSummary) {
        const summaryMatch = fullText.match(
          /(?:AI Summary|Summary|Саммари|Резюме)[\s\S]*?(?=\n\n(?:[A-ZА-Я]|$)|$)/i
        );
        
        if (summaryMatch) {
          return {
            success: true,
            content: summaryMatch[0].trim(),
          };
        }
      }

      return {
        success: true,
        content: fullText.trim(),
      };
    } else {
      return {
        success: false,
        error: 'API вернул блоки, но не удалось найти контент AI Summary',
      };
    }

  } catch (error) {
    return {
      success: false,
      error: `Ошибка при работе с Notion API: ${error.message}`,
    };
  }
}

/**
 * Главная функция извлечения данных (гибридный подход).
 * @param {string} pageId - ID страницы Notion
 * @returns {Promise<{success: boolean, content?: string, method?: string, error?: string}>}
 */
export async function extractData(pageId) {
  if (!pageId) {
    return {
      success: false,
      error: 'Не указан page_id',
    };
  }

  console.log('🚀 Запуск извлечения данных из Notion');
  console.log(`📄 Page ID: ${pageId}`);
  console.log('=' .repeat(60));

  // Метод 1: Попытка через Notion API
  const apiResult = await extractViaAPI(pageId);

  if (apiResult.success && apiResult.content) {
    console.log('');
    console.log('✅ Извлечение завершено успешно (метод: Notion API)');
    return {
      ...apiResult,
      method: 'api',
    };
  }

  console.log('');
  console.log('⚠️  Метод 1 (API) не дал результатов, переходим к методу 2 (Playwright)...');
  console.log('');

  // Метод 2: Fallback на Playwright
  const playwrightResult = await extractViaPlaywright(pageId);

  if (playwrightResult.success && playwrightResult.content) {
    console.log('');
    console.log('✅ Извлечение завершено успешно (метод: Playwright)');
    return {
      ...playwrightResult,
      method: 'playwright',
    };
  }

  // Оба метода не сработали
  console.log('');
  console.log('❌ Оба метода не дали результатов');
  return {
    success: false,
    error: `API: ${apiResult.error || 'неизвестная ошибка'}; Playwright: ${playwrightResult.error || 'неизвестная ошибка'}`,
  };
}

// Если скрипт запущен напрямую
if (import.meta.url === `file://${process.argv[1]}`) {
  const pageId = process.argv[2] || process.env.NOTION_PAGE_ID;

  if (!pageId) {
    console.error('❌ Укажите page_id как аргумент или установите NOTION_PAGE_ID в .env');
    console.error('   Использование: node index.js <page_id>');
    process.exit(1);
  }

  extractData(pageId)
    .then((result) => {
      if (result.success) {
        console.log('');
        console.log('📄 Извлеченный контент:');
        console.log('=' .repeat(60));
        console.log(result.content);
        console.log('=' .repeat(60));
        console.log(`\n✅ Метод: ${result.method}`);
        process.exit(0);
      } else {
        console.error('');
        console.error('❌ Ошибка:', result.error);
        process.exit(1);
      }
    })
    .catch((error) => {
      console.error('❌ Критическая ошибка:', error);
      process.exit(1);
    });
}
