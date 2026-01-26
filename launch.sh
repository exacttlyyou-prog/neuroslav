#!/bin/bash
# Автоматический лаунчер для запуска всей системы одной командой

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Запуск системы Digital Twin..."
echo ""

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Функция для проверки команды
check_command() {
    if command -v "$1" &> /dev/null; then
        echo -e "${GREEN}✅ $1 установлен${NC}"
        return 0
    else
        echo -e "${RED}❌ $1 не найден${NC}"
        return 1
    fi
}

# Проверка зависимостей
echo "📋 Проверка зависимостей..."
MISSING_DEPS=0

check_command python3 || MISSING_DEPS=1
check_command node || MISSING_DEPS=1
check_command brew || MISSING_DEPS=1
check_command ollama || MISSING_DEPS=1

if [ $MISSING_DEPS -eq 1 ]; then
    echo ""
    echo -e "${YELLOW}⚠️  Некоторые зависимости отсутствуют. Установите их:${NC}"
    echo "  - Python 3.11+: brew install python@3.11"
    echo "  - Node.js: brew install node"
    echo "  - Homebrew: https://brew.sh"
    echo "  - Ollama: https://ollama.ai"
    exit 1
fi

# Проверка BlackHole
echo ""
echo "🔊 Проверка BlackHole..."
if brew list blackhole-2ch &> /dev/null; then
    echo -e "${GREEN}✅ BlackHole установлен${NC}"
    
    # Проверяем, есть ли BlackHole в списке аудио-устройств через system_profiler
    if system_profiler SPAudioDataType 2>/dev/null | grep -q "BlackHole"; then
        echo -e "${GREEN}✅ BlackHole доступен в системе${NC}"
    else
        echo -e "${YELLOW}⚠️  BlackHole установлен, но не виден в системе${NC}"
        echo -e "${YELLOW}   Может потребоваться перезагрузка Mac${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  BlackHole не установлен. Устанавливаю...${NC}"
    brew install blackhole-2ch
    echo -e "${YELLOW}⚠️  После установки BlackHole может потребоваться перезагрузка Mac${NC}"
    echo -e "${YELLOW}   Также нужно создать Multi-Output Device через Audio MIDI Setup${NC}"
    echo -e "${YELLOW}   См. инструкцию в QUICK_START.md${NC}"
fi

# Проверка виртуального окружения Python
echo ""
echo "🐍 Проверка Python окружения..."
if [ ! -d "apps/api/.venv" ]; then
    echo -e "${YELLOW}⚠️  Виртуальное окружение не найдено. Создаю...${NC}"
    cd apps/api
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    cd "$SCRIPT_DIR"
else
    echo -e "${GREEN}✅ Виртуальное окружение найдено${NC}"
fi

# Проверка Node.js зависимостей
echo ""
echo "📦 Проверка Node.js зависимостей..."
if [ -d "apps/web" ]; then
    if [ ! -d "apps/web/node_modules" ]; then
        echo -e "${YELLOW}⚠️  Node.js зависимости не установлены. Устанавливаю...${NC}"
        cd apps/web
        npm install
        cd "$SCRIPT_DIR"
    else
        echo -e "${GREEN}✅ Node.js зависимости установлены${NC}"
    fi
fi

# Проверка зависимостей agent-worker
if [ -d "apps/agent-worker" ]; then
    echo ""
    echo "🤖 Проверка зависимостей Agent Worker..."
    if [ ! -d "apps/agent-worker/node_modules" ]; then
        echo -e "${YELLOW}⚠️  Зависимости Agent Worker не установлены. Устанавливаю...${NC}"
        cd apps/agent-worker
        npm install
        cd "$SCRIPT_DIR"
    else
        echo -e "${GREEN}✅ Зависимости Agent Worker установлены${NC}"
    fi
    
    # Проверка наличия скомпилированного кода
    if [ ! -d "apps/agent-worker/dist" ]; then
        echo -e "${YELLOW}⚠️  Код не скомпилирован. Компилирую...${NC}"
        cd apps/agent-worker
        npm run build
        cd "$SCRIPT_DIR"
    fi
fi

# Проверка Ollama
echo ""
echo "🤖 Проверка Ollama..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Ollama запущен${NC}"
else
    echo -e "${YELLOW}⚠️  Ollama не запущен. Запускаю в фоне...${NC}"
    ollama serve > /dev/null 2>&1 &
    OLLAMA_PID=$!
    sleep 2
    echo -e "${GREEN}✅ Ollama запущен (PID: $OLLAMA_PID)${NC}"
fi

# Проверка .env файла
echo ""
echo "⚙️  Проверка конфигурации..."
if [ -f ".env" ]; then
    echo "✅ Файл .env найден в корне проекта"
    # Синхронизируем с бэкендом
    cp .env apps/api/.env
elif [ -f "apps/api/.env" ]; then
    echo "✅ Файл .env найден в apps/api/"
else
    echo -e "${YELLOW}⚠️  Файл .env не найден${NC}"
    echo "   Создайте .env файл в корне проекта"
fi

# Функция для очистки при выходе
cleanup() {
    echo ""
    echo "🛑 Остановка сервисов..."
    kill $BACKEND_PID $FRONTEND_PID $AGENT_WORKER_PID 2>/dev/null || true
    if [ ! -z "$OLLAMA_PID" ]; then
        kill $OLLAMA_PID 2>/dev/null || true
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

# Запуск бэкенда
echo ""
echo "🔧 Запуск FastAPI Backend..."
cd apps/api
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/digital_twin_backend.log 2>&1 &
BACKEND_PID=$!
cd "$SCRIPT_DIR"
echo -e "${GREEN}✅ Backend запущен (PID: $BACKEND_PID, порт 8000)${NC}"

# Запуск фронтенда (если есть)
if [ -d "apps/web" ]; then
    echo ""
    echo "🎨 Запуск Next.js Frontend..."
    cd apps/web
    npm run dev > /tmp/digital_twin_frontend.log 2>&1 &
    FRONTEND_PID=$!
    cd "$SCRIPT_DIR"
    echo -e "${GREEN}✅ Frontend запущен (PID: $FRONTEND_PID, порт 3000)${NC}"
fi

# Запуск Agent Worker (мульти-агентная система обработки встреч)
if [ -d "apps/agent-worker" ]; then
    echo ""
    echo "🤖 Запуск Agent Worker (обработка AI Meeting Notes)..."
    cd apps/agent-worker
    # Проверяем наличие .env файла
    if [ ! -f ".env" ] && [ -f "../../.env" ]; then
        echo -e "${YELLOW}⚠️  Копирую .env из корня проекта...${NC}"
        cp ../../.env .env
    fi
    # Проверяем наличие обязательных переменных
    if [ -f ".env" ]; then
        # Запускаем в фоновом режиме
        npm start > /tmp/digital_twin_agent_worker.log 2>&1 &
        AGENT_WORKER_PID=$!
        cd "$SCRIPT_DIR"
        echo -e "${GREEN}✅ Agent Worker запущен (PID: $AGENT_WORKER_PID)${NC}"
        echo -e "${GREEN}   Логи: tail -f /tmp/digital_twin_agent_worker.log${NC}"
    else
        echo -e "${YELLOW}⚠️  Agent Worker пропущен: не найден .env файл${NC}"
        echo -e "${YELLOW}   Создайте .env в apps/agent-worker/ или в корне проекта${NC}"
        cd "$SCRIPT_DIR"
    fi
fi

# Ожидание запуска сервисов
echo ""
echo "⏳ Ожидание запуска сервисов..."
sleep 5

# Проверка статуса
echo ""
echo "📊 Статус сервисов:"
echo ""

check_service() {
    local name=$1
    local url=$2
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ $name: работает${NC} ($url)"
            return 0
        fi
        if [ $attempt -lt $max_attempts ]; then
            sleep 1
        fi
        attempt=$((attempt + 1))
    done
    
    echo -e "${RED}❌ $name: не отвечает${NC} ($url)"
    return 1
}

check_service "FastAPI Backend" "http://127.0.0.1:8000/health"
FRONTEND_OK=0
FRONTEND_PORT=3000
if [ -d "apps/web" ]; then
    # Проверяем оба возможных порта
    if check_service "Next.js Frontend" "http://127.0.0.1:3000"; then
        FRONTEND_OK=1
        FRONTEND_PORT=3000
    elif check_service "Next.js Frontend" "http://127.0.0.1:3001"; then
        FRONTEND_OK=1
        FRONTEND_PORT=3001
        echo -e "${YELLOW}⚠️  Фронтенд запущен на порту 3001 (3000 занят)${NC}"
    fi
fi
check_service "Ollama" "http://127.0.0.1:11434/api/tags"

# Автоматическое открытие фронтенда в режиме приложения
if [ -d "apps/web" ] && [ $FRONTEND_OK -eq 1 ]; then
    echo ""
    echo "🌐 Открываю фронтенд в режиме приложения..."
    
    # Ищем Google Chrome (проверяем несколько возможных путей)
    CHROME_PATH=""
    
    # Стандартный путь
    if [ -f "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
        CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    # Альтернативный путь (если установлен через Homebrew)
    elif [ -f "/opt/homebrew/bin/google-chrome" ]; then
        CHROME_PATH="/opt/homebrew/bin/google-chrome"
    elif [ -f "/usr/local/bin/google-chrome" ]; then
        CHROME_PATH="/usr/local/bin/google-chrome"
    fi
    
    FRONTEND_URL="http://localhost:${FRONTEND_PORT}"
    
    if [ -n "$CHROME_PATH" ]; then
        # Небольшая задержка для полной загрузки фронтенда
        sleep 1
        # Запускаем Chrome в режиме приложения (без вкладок, адресной строки)
        "$CHROME_PATH" --app="$FRONTEND_URL" > /dev/null 2>&1 &
        echo -e "${GREEN}✅ Фронтенд открыт в режиме приложения (Chrome) на порту ${FRONTEND_PORT}${NC}"
    else
        # Fallback: открываем в стандартном браузере
        sleep 1
        open "$FRONTEND_URL" > /dev/null 2>&1
        echo -e "${YELLOW}⚠️  Chrome не найден, открываю в стандартном браузере${NC}"
        echo -e "${YELLOW}   Для режима приложения установите Google Chrome${NC}"
    fi
fi

echo ""
echo "=" 
echo -e "${GREEN}✨ Система запущена!${NC}"
echo ""
echo "📍 Доступные сервисы:"
echo "   - Backend API: http://localhost:8000"
echo "   - API Docs: http://localhost:8000/docs"
if [ -d "apps/web" ] && [ $FRONTEND_OK -eq 1 ]; then
    echo "   - Frontend: http://localhost:${FRONTEND_PORT}"
fi
echo "   - Ollama: http://localhost:11434"
echo ""
echo "📝 Логи:"
echo "   - Backend: tail -f /tmp/digital_twin_backend.log"
echo "   - Frontend: tail -f /tmp/digital_twin_frontend.log"
if [ -d "apps/agent-worker" ]; then
    echo "   - Agent Worker: tail -f /tmp/digital_twin_agent_worker.log"
fi
echo ""
echo "⏹  Для остановки нажмите Ctrl+C"
echo ""

# Ожидание
wait
