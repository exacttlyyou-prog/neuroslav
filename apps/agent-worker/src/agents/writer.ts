/**
 * Агент-Секретарь: создает задачи в Notion и обновляет страницу встречи
 */

import { Client } from '@notionhq/client';
import { WriterResult, StructuredMeetingData } from '../types.js';
import { logger } from '../utils/logger.js';

/**
 * Создание задач в базе данных Notion
 */
export async function createTasks(
  notion: Client,
  tasksDbId: string,
  actionItems: StructuredMeetingData['actionItems']
): Promise<string[]> {
  const taskIds: string[] = [];

  for (const item of actionItems) {
    try {
      const properties: Record<string, any> = {
        Name: {
          title: [
            {
              text: {
                content: item.title,
              },
            },
          ],
        },
      };

      // Добавляем описание, если есть
      if (item.description) {
        properties.Description = {
          rich_text: [
            {
              text: {
                content: item.description,
              },
            },
          ],
        };
      }

      // Добавляем ответственного, если есть
      if (item.assignee) {
        // ВАЖНО: Адаптируйте под структуру вашей БД!
        // Если поле "Assignee" типа "People", используйте:
        // properties.Assignee = { people: [{ id: userId }] };
        // Если типа "Rich Text", используйте текущий вариант:
        properties.Assignee = {
          rich_text: [
            {
              text: {
                content: item.assignee,
              },
            },
          ],
        };
      }

      // Добавляем дату выполнения, если есть
      if (item.dueDate) {
        properties['Due Date'] = {
          date: {
            start: item.dueDate,
          },
        };
      }

      // Добавляем приоритет, если есть
      if (item.priority) {
        properties.Priority = {
          select: {
            name: item.priority,
          },
        };
      }

      const response = await notion.pages.create({
        parent: {
          database_id: tasksDbId,
        },
        properties,
      });

      taskIds.push(response.id);
      logger.info(`✅ Создана задача: ${item.title} (${response.id})`);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      logger.error(`❌ Ошибка при создании задачи "${item.title}": ${errorMessage}`);
      // Продолжаем создавать остальные задачи
    }
  }

  return taskIds;
}

/**
 * Обновление страницы встречи: добавление ссылок на созданные задачи
 */
export async function updateMeetingPage(
  notion: Client,
  pageId: string,
  taskIds: string[],
  summary?: string
): Promise<void> {
  try {
    // Получаем информацию о странице для формирования ссылок
    const taskLinks: Array<{ type: 'page'; page: { id: string } }> = taskIds.map((id) => ({
      type: 'page',
      page: { id },
    }));

    // Добавляем блок с ссылками на задачи
    if (taskLinks.length > 0) {
      await notion.blocks.children.append({
        block_id: pageId,
        children: [
          {
            object: 'block',
            type: 'heading_2',
            heading_2: {
              rich_text: [
                {
                  type: 'text',
                  text: {
                    content: '📋 Созданные задачи',
                  },
                },
              ],
            },
          },
          {
            object: 'block',
            type: 'bulleted_list_item',
            bulleted_list_item: {
              rich_text: [
                {
                  type: 'text',
                  text: {
                    content: `Создано ${taskIds.length} задач из встречи`,
                  },
                },
              ],
            },
          },
        ],
      });

      logger.info(`✅ Добавлены ссылки на ${taskIds.length} задач в страницу встречи`);
    }

    // Если есть summary, добавляем его как callout
    if (summary) {
      await notion.blocks.children.append({
        block_id: pageId,
        children: [
          {
            object: 'block',
            type: 'callout',
            callout: {
              rich_text: [
                {
                  type: 'text',
                  text: {
                    content: summary,
                  },
                },
              ],
              icon: {
                emoji: '✅',
              },
            },
          },
        ],
      });

      logger.info('✅ Добавлено резюме встречи на страницу');
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    logger.error(`❌ Ошибка при обновлении страницы встречи: ${errorMessage}`);
    throw error;
  }
}

/**
 * Главная функция Writer Agent
 */
export async function writeToNotion(
  notion: Client,
  meetingPageId: string,
  tasksDbId: string,
  data: StructuredMeetingData
): Promise<WriterResult> {
  logger.info('📝 Запись данных в Notion...');

  try {
    // Создаем задачи
    const taskIds = await createTasks(notion, tasksDbId, data.actionItems);

    if (taskIds.length === 0 && data.actionItems.length > 0) {
      return {
        success: false,
        error: 'Не удалось создать ни одной задачи',
      };
    }

    // Обновляем страницу встречи
    await updateMeetingPage(notion, meetingPageId, taskIds, data.summary);

    logger.info(`✅ Успешно создано ${taskIds.length} задач и обновлена страница встречи`);

    return {
      success: true,
      taskIds,
    };
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    logger.error(`❌ Ошибка при записи в Notion: ${errorMessage}`);
    return {
      success: false,
      error: `Ошибка при записи в Notion: ${errorMessage}`,
    };
  }
}
