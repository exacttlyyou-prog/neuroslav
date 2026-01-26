/**
 * Агент-Аналитик: извлекает структурированные данные из сырого текста через LLM
 */

import OpenAI from 'openai';
import { AnalystResult, StructuredMeetingData, ActionItem, KeyDecision } from '../types.js';
import { logger } from '../utils/logger.js';

/**
 * Промпт для извлечения структурированных данных из текста встречи
 */
const EXTRACTION_PROMPT = `Ты анализируешь текст встречи из Notion AI Meeting Notes. 
Извлеки из текста следующую информацию и верни ТОЛЬКО валидный JSON объект без дополнительных комментариев.

Требования к структуре JSON:
1. Action Items (задачи) - массив объектов с полями:
   - title: краткое название задачи (обязательно)
   - description: подробное описание (опционально)
   - assignee: имя ответственного (опционально)
   - dueDate: дата выполнения в формате YYYY-MM-DD (опционально)
   - priority: "High", "Medium" или "Low" (опционально)

2. Key Decisions (ключевые решения) - массив объектов с полями:
   - title: краткое название решения (обязательно)
   - description: подробное описание (опционально)
   - context: контекст решения (опционально)

3. Summary (краткое резюме) - опциональное поле со строкой

Пример правильного формата:
{
  "actionItems": [
    {
      "title": "Название задачи",
      "description": "Описание",
      "assignee": "Имя",
      "dueDate": "2024-01-25",
      "priority": "High"
    }
  ],
  "keyDecisions": [
    {
      "title": "Название решения",
      "description": "Описание",
      "context": "Контекст"
    }
  ],
  "summary": "Краткое резюме встречи"
}

Если какой-то массив пуст, верни пустой массив []. Если summary отсутствует, можешь его не включать. ВАЖНО: верни только JSON объект, никакого дополнительного текста.`;

/**
 * Извлечение структурированных данных из текста через OpenAI
 */
export async function analyzeMeetingContent(
  rawText: string,
  apiKey: string
): Promise<AnalystResult> {
  logger.info('🤖 Анализ контента через OpenAI...');

  try {
    const openai = new OpenAI({ apiKey });

    const response = await openai.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [
        {
          role: 'system',
          content: EXTRACTION_PROMPT,
        },
        {
          role: 'user',
          content: `Проанализируй следующий текст встречи:\n\n${rawText}`,
        },
      ],
      temperature: 0.3,
      response_format: { type: 'json_object' },
    });

    const content = response.choices[0]?.message?.content;
    if (!content) {
      return {
        success: false,
        error: 'OpenAI не вернул контент',
      };
    }

    // Парсим JSON ответ
    let parsedData: StructuredMeetingData;
    try {
      const jsonData = JSON.parse(content);
      
      // Валидация и нормализация структуры
      parsedData = {
        actionItems: Array.isArray(jsonData.actionItems)
          ? jsonData.actionItems.map((item: any) => ({
              title: item.title || '',
              description: item.description,
              assignee: item.assignee,
              dueDate: item.dueDate,
              priority: item.priority,
            }))
          : [],
        keyDecisions: Array.isArray(jsonData.keyDecisions)
          ? jsonData.keyDecisions.map((decision: any) => ({
              title: decision.title || '',
              description: decision.description,
              context: decision.context,
            }))
          : [],
        summary: jsonData.summary,
      };

      logger.info(
        `✅ Анализ завершен: ${parsedData.actionItems.length} задач, ` +
        `${parsedData.keyDecisions.length} решений`
      );

      return {
        success: true,
        data: parsedData,
      };
    } catch (parseError) {
      logger.error(`❌ Ошибка парсинга JSON: ${parseError}`);
      logger.debug(`Сырой ответ: ${content}`);
      return {
        success: false,
        error: `Невалидный JSON от OpenAI: ${parseError}`,
      };
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    logger.error(`❌ Ошибка при анализе контента: ${errorMessage}`);
    return {
      success: false,
      error: `Ошибка при анализе контента: ${errorMessage}`,
    };
  }
}
