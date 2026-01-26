/**
 * Общий экземпляр клиента Notion API
 */

import { Client } from '@notionhq/client';
import { logger } from './logger.js';

let notionClient: Client | null = null;

export function getNotionClient(token: string): Client {
  if (!notionClient) {
    notionClient = new Client({ auth: token });
    logger.info('✅ Notion клиент инициализирован');
  }
  return notionClient;
}

export function resetNotionClient(): void {
  notionClient = null;
}
