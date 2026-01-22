/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Настройка для загрузки файлов
  serverRuntimeConfig: {
    maxFileSize: '10mb',
  },
  // Переменные окружения
  env: {
    OPENAI_API_KEY: process.env.OPENAI_API_KEY,
  },
}

module.exports = nextConfig
