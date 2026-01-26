#!/bin/bash
# Быстрый запуск записи встречи

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🎙 Запуск записи встречи..."
echo ""

# Активируем виртуальное окружение
cd apps/api
source .venv/bin/activate

# Запускаем скрипт записи
python scripts/record_meeting.py
