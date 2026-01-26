/**
 * Скрипт для настройки авторизации Notion через браузер
 * Создает auth.json с сохраненным состоянием сессии
 */

import { chromium } from 'playwright';
import { writeFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const AUTH_FILE = join(__dirname, '../../auth.json');

async function setupAuth() {
  console.log('🔐 Настройка авторизации Notion через браузер\n');
  console.log('📋 Инструкция:');
  console.log('1. Браузер откроется автоматически');
  console.log('2. Войдите в свой аккаунт Notion');
  console.log('3. После успешного входа закройте браузер');
  console.log('4. Состояние сессии будет сохранено в auth.json\n');

  const browser = await chromium.launch({
    headless: false, // Показываем браузер для входа
  });

  try {
    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
    });

    const page = await context.newPage();

    // Переходим на главную страницу Notion
    console.log('🌐 Открываем Notion...');
    await page.goto('https://www.notion.so', {
      waitUntil: 'networkidle',
      timeout: 30000,
    });

    console.log('\n⏳ Ожидание входа в Notion...');
    console.log('   После входа нажмите Enter в терминале...\n');

    // Ждем, пока пользователь войдет
    await new Promise<void>((resolve) => {
      process.stdin.once('data', () => {
        resolve();
      });
    });

    // Сохраняем состояние сессии
    const storageState = await context.storageState();
    writeFileSync(AUTH_FILE, JSON.stringify(storageState, null, 2));

    console.log(`\n✅ Состояние сессии сохранено в ${AUTH_FILE}`);
    console.log('   Теперь можно использовать этот файл для автоматической авторизации\n');
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`❌ Ошибка: ${errorMessage}`);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

setupAuth();
