#!/bin/bash
# Скрипт для создания .app bundle

# Переходим в директорию скрипта
cd "$(dirname "$0")"

APP_NAME="DigitalTwin"
APP_DIR="${APP_NAME}.app"

echo "📦 Создание .app bundle для $APP_NAME..."

# Удаляем старый bundle
rm -rf "$APP_DIR"

# Создаем структуру
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Создаем Info.plist
cat > "$APP_DIR/Contents/Info.plist" <<'PLIST_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIdentifier</key>
    <string>com.digitaltwin.launcher</string>
    <key>CFBundleName</key>
    <string>DigitalTwin</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
</dict>
</plist>
PLIST_EOF

# Создаем лаунчер
cat > "$APP_DIR/Contents/MacOS/launcher" <<'LAUNCHER_EOF'
#!/bin/bash
# Абсолютный путь к папке проекта
PROJECT_DIR="/Users/slava/Desktop/коллеги, обсудили"

# Проверяем, существует ли launch.sh
if [ ! -f "$PROJECT_DIR/launch.sh" ]; then
    osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    do script "echo '❌ Ошибка: не найден launch.sh в $PROJECT_DIR'"
end tell
APPLESCRIPT
    exit 1
fi

# Запускаем launch.sh в новом окне терминала
osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    do script "cd '$PROJECT_DIR' && ./launch.sh"
end tell
APPLESCRIPT
LAUNCHER_EOF

# Делаем файлы исполняемыми
chmod +x "$APP_DIR/Contents/MacOS/launcher"
chmod +x "launch.sh"

echo "✅ $APP_DIR успешно создан!"
echo "📍 Теперь вы можете скопировать его на Рабочий стол."