# Инструкция по установке и настройке BlackHole для захвата системного звука

## 1. Установка BlackHole

```bash
brew install blackhole-2ch
```

После установки перезагрузите Mac (или перезапустите аудио-систему).

## 2. Настройка Multi-Output Device в macOS (Tahoe и новее)

**Важно:** В macOS Tahoe опция Multi-Output Device находится в **Audio MIDI Setup**, а не в системных настройках!

Для того, чтобы слышать звук в наушниках И одновременно записывать системный звук через BlackHole:

1. Откройте **Audio MIDI Setup** (через Spotlight: `Cmd+Space`, введите "Audio MIDI Setup")
2. В меню **Window** выберите **Show Audio Devices** (или нажмите `Cmd+2`)
3. Нажмите кнопку **+** (внизу слева) и выберите **Create Multi-Output Device**
4. В списке устройств отметьте галочками:
   - Ваши наушники/колонки (основной выход, например "AirPods Pro")
   - **BlackHole 2ch** (для записи)
5. Закройте Audio MIDI Setup

**Альтернативный способ (через терминал):**
```bash
# Создать Multi-Output Device автоматически (после установки BlackHole)
# Этот скрипт будет в лаунчере
```

## 3. Использование

После настройки:
- Выберите **Multi-Output Device** как устройство вывода по умолчанию
- Звук будет идти и в ваши наушники, и в BlackHole
- Скрипт `record_meeting.py` автоматически найдет BlackHole и будет записывать системный звук

## Проверка установки

После установки BlackHole должен появиться в списке аудио-устройств. Проверить можно командой:

```bash
python -c "import sounddevice as sd; print([d['name'] for d in sd.query_devices() if 'blackhole' in d['name'].lower()])"
```

Если видите `['BlackHole 2ch']` - всё готово!
