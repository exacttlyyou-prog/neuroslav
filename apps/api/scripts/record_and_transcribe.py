import asyncio
import sys
import os
import wave
import numpy as np
import sounddevice as sd
from pathlib import Path
from datetime import datetime
from loguru import logger

# Добавляем путь к приложению
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.services.transcription_service import transcription_service
from app.services.notion_service import NotionService
from app.services.telegram_service import TelegramService
from app.config import get_settings

# Параметры аудио
FS = 16000  # Частота дискретизации (Whisper любит 16кГц)
CHANNELS = 1

async def record_audio(duration=None):
    """Записывает аудио с микрофона."""
    logger.info("🎤 Запись пошла! Говорите...")
    print("\n--- ЗАПИСЬ ИДЕТ. Нажмите ENTER, чтобы остановить и начать транскрипцию ---\n")
    
    recording = []
    
    def callback(indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        recording.append(indata.copy())

    # Используем InputStream в контексте, но ждем ввода пользователя для остановки
    stream = sd.InputStream(samplerate=FS, channels=CHANNELS, callback=callback)
    with stream:
        loop = asyncio.get_running_loop()
        # Ждем нажатия Enter (чтение строки из stdin) в отдельном потоке
        await loop.run_in_executor(None, sys.stdin.readline)
    
    logger.info("⏹ Запись остановлена пользователем.")
    
    if not recording:
        return None
        
    return np.concatenate(recording, axis=0)

def save_wav(data, filename):
    """Сохраняет массив numpy в WAV файл."""
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2) # 16-bit
        wf.setframerate(FS)
        # Конвертируем float32 -> int16
        audio_int16 = (data * 32767).astype(np.int16)
        wf.writeframes(audio_int16.tobytes())

async def main():
    logger.info("🚀 Запуск MVP локальной транскрипции")
    
    # 1. Записываем голос
    audio_data = await record_audio()
    if audio_data is None:
        logger.error("❌ Ничего не записано")
        return

    # 2. Сохраняем во временный файл
    temp_dir = Path(project_root / "data" / "temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    
    save_wav(audio_data, str(temp_file))
    logger.info(f"💾 Файл сохранен: {temp_file}")

    # 3. Транскрибируем
    text = await transcription_service.transcribe(temp_file)
    if not text:
        logger.error("❌ Не удалось получить текст")
        return

    print(f"\n📝 РЕЗУЛЬТАТ ТРАНСКРИПЦИИ:\n{'='*30}\n{text}\n{'='*30}\n")

    # 4. Отправляем в Notion
    settings = get_settings()
    page_id = settings.notion_meeting_page_id
    
    if page_id:
        logger.info(f"📤 Сохранение в Notion на страницу {page_id}...")
        notion = NotionService()
        
        # Формируем красивый заголовок для блока
        now = datetime.now().strftime("%H:%M:%S")
        summary_text = f"🎙 Локальная запись ({now}):\n{text}"
        
        await notion.save_meeting_summary(page_id, summary_text)
        logger.info("✅ Успешно сохранено в Notion")
        
        # 5. Шлем в Telegram (опционально)
        try:
            telegram = TelegramService()
            await telegram.send_notification(f"<b>🆕 Новая локальная запись</b>\n\n{text}")
            logger.info("✅ Уведомление в Telegram отправлено")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отправить в Telegram: {e}")
    else:
        logger.warning("⚠️ NOTION_MEETING_PAGE_ID не найден, сохранение пропущено")

    # Удаляем временный файл (опционально)
    # os.remove(temp_file)

if __name__ == "__main__":
    asyncio.run(main())
