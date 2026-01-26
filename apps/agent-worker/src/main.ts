/**
 * Точка входа в приложение
 */

import { runCoordinator } from './coordinator.js';
import { logger } from './utils/logger.js';

async function main() {
  try {
    await runCoordinator();
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    logger.error(`❌ Критическая ошибка: ${errorMessage}`);
    process.exit(1);
  }
}

// Обработка сигналов для graceful shutdown
process.on('SIGINT', () => {
  logger.info('\n🛑 Получен сигнал SIGINT, завершение работы...');
  process.exit(0);
});

process.on('SIGTERM', () => {
  logger.info('\n🛑 Получен сигнал SIGTERM, завершение работы...');
  process.exit(0);
});

main();
