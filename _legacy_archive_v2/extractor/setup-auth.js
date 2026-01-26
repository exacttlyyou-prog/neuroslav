#!/usr/bin/env node
/**
 * Скрипт для ручной настройки аутентификации в Notion (опциональный).
 * Используется только если автоматическая авторизация через токен не работает.
 * Запускает браузер в видимом режиме, пользователь вручную логинится,
 * затем сохраняется состояние сессии в notion-auth.json.
 */
import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { existsSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const AUTH_FILE = join(__dirname, 'notion-auth.json');

async function setupAuth() {
  console.log('🔐 Настройка аутентификации Notion (опционально)');
  console.log('=' .repeat(60));
  console.log('Примечание: Этот скрипт нужен только если автоматическая');
  console.log('авторизация через NOTION_TOKEN не работает.');
  console.log('=' .repeat(60));
  console.log('');
  
  // Проверяем, существует ли уже файл аутентификации
  if (existsSync(AUTH_FILE)) {
    console.log(`⚠️  Файл ${AUTH_FILE} уже существует.`);
    console.log('   Если хотите обновить сессию, удалите файл и запустите скрипт снова.');
    return;
  }

  console.log('📱 Запуск браузера...');
  const browser = await chromium.launch({
    headless: false, // Видимый браузер для ручного входа
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
  });

  const page = await context.newPage();

  try {
    console.log('🌐 Переход на страницу входа Notion...');
    await page.goto('https://www.notion.so/login', {
      waitUntil: 'networkidle',
    });

    console.log('');
    console.log('=' .repeat(60));
    console.log('📋 ИНСТРУКЦИЯ:');
    console.log('=' .repeat(60));
    console.log('1. В открывшемся браузере войдите в свой аккаунт Notion');
    console.log('2. Пройдите все этапы аутентификации (2FA, SSO и т.д.)');
    console.log('3. Дождитесь загрузки рабочего пространства');
    console.log('4. Скрипт автоматически сохранит сессию через 60 секунд');
    console.log('=' .repeat(60));
    console.log('');

    // Ждем, пока URL изменится на рабочее пространство (успешный вход)
    console.log('⏳ Ожидание успешного входа...');
    console.log('   (Максимальное время ожидания: 60 секунд)');

    let loginSuccessful = false;
    const maxWaitTime = 60000; // 60 секунд
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitTime) {
      const currentUrl = page.url();
      
      // Проверяем, что мы не на странице логина
      if (!currentUrl.includes('/login') && currentUrl.includes('notion.so')) {
        // Дополнительно ждем немного, чтобы убедиться, что страница загрузилась
        await page.waitForTimeout(2000);
        loginSuccessful = true;
        break;
      }

      await page.waitForTimeout(1000);
    }

    if (!loginSuccessful) {
      throw new Error('Не удалось определить успешный вход. Убедитесь, что вы вошли в Notion.');
    }

    console.log('✅ Вход успешен! Сохранение состояния сессии...');

    // Сохраняем состояние сессии
    await context.storageState({ path: AUTH_FILE });

    console.log(`✅ Состояние сессии сохранено в: ${AUTH_FILE}`);
    console.log('   Теперь можно использовать extract.js для автоматического извлечения данных.');

  } catch (error) {
    console.error('❌ Ошибка при настройке аутентификации:', error.message);
    throw error;
  } finally {
    await browser.close();
  }
}

// Запуск скрипта
setupAuth()
  .then(() => {
    console.log('');
    console.log('✅ Настройка завершена успешно!');
    process.exit(0);
  })
  .catch((error) => {
    console.error('');
    console.error('❌ Ошибка:', error.message);
    process.exit(1);
  });
