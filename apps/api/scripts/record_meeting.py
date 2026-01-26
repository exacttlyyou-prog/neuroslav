"""
Скрипт для потоковой записи встреч с автоматической транскрипцией чанками.
Захватывает микрофон + системный звук (BlackHole) и транскрибирует каждые 30 секунд.
"""
import asyncio
import sys
import os
import signal
import wave
import numpy as np
import sounddevice as sd
from pathlib import Path
from datetime import datetime
from collections import deque
from loguru import logger
from typing import Optional, Tuple

# Добавляем путь к приложению
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.services.transcription_service import transcription_service
from app.services.notion_service import NotionService
from app.services.telegram_service import TelegramService
from app.services.ollama_service import OllamaService
from app.config import get_settings

# Параметры аудио
FS = 16000  # Частота дискретизации (Whisper любит 16кГц)
CHANNELS = 1
CHUNK_DURATION = 30  # Длительность чанка в секундах для транскрипции
CHUNK_SAMPLES = FS * CHUNK_DURATION  # Количество сэмплов в чанке


def find_audio_devices() -> Tuple[Optional[int], Optional[int]]:
    """
    Находит устройства для записи: микрофон и BlackHole.
    
    Returns:
        Tuple[mic_device_id, blackhole_device_id]
    """
    devices = sd.query_devices()
    mic_id = None
    blackhole_id = None
    
    for i, device in enumerate(devices):
        name_lower = device['name'].lower()
        if device['max_input_channels'] > 0:
            if 'blackhole' in name_lower:
                blackhole_id = i
                logger.info(f"✅ Найден BlackHole: {device['name']} (ID: {i})")
            elif mic_id is None:  # Первое доступное устройство ввода (обычно микрофон)
                mic_id = i
                logger.info(f"✅ Найден микрофон: {device['name']} (ID: {i})")
    
    if blackhole_id is None:
        logger.warning("⚠️ BlackHole не найден. Будет использоваться только микрофон.")
        logger.warning("   Установите: brew install blackhole-2ch")
    
    return mic_id, blackhole_id


def mix_audio_streams(mic_data: np.ndarray, system_data: Optional[np.ndarray]) -> np.ndarray:
    """
    Смешивает два аудио-потока в один.
    
    Args:
        mic_data: Данные с микрофона
        system_data: Данные с системного звука (BlackHole) или None
        
    Returns:
        Смешанный аудио-массив
    """
    if system_data is None:
        return mic_data
    
    # Нормализуем оба потока и смешиваем (50/50)
    # Если длины разные, обрезаем до минимальной
    min_len = min(len(mic_data), len(system_data))
    mixed = (mic_data[:min_len] * 0.5 + system_data[:min_len] * 0.5)
    
    # Предотвращаем клиппинг
    mixed = np.clip(mixed, -1.0, 1.0)
    return mixed


class ChunkedAudioRecorder:
    """Класс для записи аудио с автоматической нарезкой на чанки."""
    
    def __init__(self, mic_device: Optional[int], blackhole_device: Optional[int]):
        self.mic_device = mic_device
        self.blackhole_device = blackhole_device
        self.mic_buffer = deque()
        self.system_buffer = deque()
        self.is_recording = False
        self.chunk_queue = asyncio.Queue()
        
    def mic_callback(self, indata, frames, time, status):
        """Callback для микрофона."""
        if status:
            logger.warning(f"Микрофон статус: {status}")
        if self.is_recording:
            self.mic_buffer.append(indata.copy())
    
    def system_callback(self, indata, frames, time, status):
        """Callback для системного звука (BlackHole)."""
        if status:
            logger.warning(f"BlackHole статус: {status}")
        if self.is_recording:
            # Проверяем, не тишина ли это (все значения близки к нулю)
            audio_level = np.abs(indata).max()
            if audio_level < 0.001:  # Порог тишины
                if not hasattr(self, '_silence_warning_logged'):
                    self._silence_warning_logged = True
                    logger.warning("⚠️ BlackHole получает только тишину. Проверьте настройки 'Multi-Output Device' в macOS: Системные настройки → Звук → Выход")
            else:
                self._silence_warning_logged = False
            self.system_buffer.append(indata.copy())
    
    async def start_recording(self):
        """Запускает запись с обоих устройств."""
        self.is_recording = True
        self.mic_buffer.clear()
        self.system_buffer.clear()
        
        streams = []
        
        # Запускаем поток микрофона
        if self.mic_device is not None:
            mic_stream = sd.InputStream(
                device=self.mic_device,
                samplerate=FS,
                channels=CHANNELS,
                callback=self.mic_callback
            )
            mic_stream.start()
            streams.append(mic_stream)
            logger.info("🎤 Микрофон: запись начата")
        
        # Запускаем поток BlackHole (если доступен)
        if self.blackhole_device is not None:
            system_stream = sd.InputStream(
                device=self.blackhole_device,
                samplerate=FS,
                channels=CHANNELS,
                callback=self.system_callback
            )
            system_stream.start()
            streams.append(system_stream)
            logger.info("🔊 BlackHole: запись начата")
        
        return streams
    
    def stop_recording(self, streams):
        """Останавливает запись."""
        self.is_recording = False
        for stream in streams:
            stream.stop()
            stream.close()
        logger.info("⏹ Запись остановлена")
    
    async def extract_chunk(self) -> Optional[np.ndarray]:
        """
        Извлекает один чанк (30 сек) из буферов и смешивает их.
        
        Returns:
            Смешанный аудио-чанк или None, если данных недостаточно
        """
        # Считаем, сколько сэмплов нужно для чанка
        needed_samples = CHUNK_SAMPLES
        
        # Собираем данные из буферов
        mic_chunk = []
        system_chunk = []
        
        mic_samples = 0
        system_samples = 0
        
        # Собираем микрофон
        while mic_samples < needed_samples and self.mic_buffer:
            chunk = self.mic_buffer.popleft()
            mic_chunk.append(chunk)
            mic_samples += len(chunk)
        
        # Собираем системный звук (если есть)
        if self.blackhole_device is not None:
            while system_samples < needed_samples and self.system_buffer:
                chunk = self.system_buffer.popleft()
                system_chunk.append(chunk)
                system_samples += len(chunk)
        
        if not mic_chunk:
            return None
        
        # Объединяем чанки
        mic_data = np.concatenate(mic_chunk, axis=0) if mic_chunk else np.array([])
        system_data = np.concatenate(system_chunk, axis=0) if system_chunk else None
        
        # Обрезаем до нужной длины
        if len(mic_data) > needed_samples:
            mic_data = mic_data[:needed_samples]
        if system_data is not None and len(system_data) > needed_samples:
            system_data = system_data[:needed_samples]
        
        # Смешиваем
        mixed = mix_audio_streams(mic_data, system_data)
        
        return mixed
    
    def save_chunk_to_wav(self, data: np.ndarray, filename: Path):
        """Сохраняет чанк в WAV файл."""
        with wave.open(str(filename), 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(FS)
            audio_int16 = (data * 32767).astype(np.int16)
            wf.writeframes(audio_int16.tobytes())


async def transcription_worker(
    chunk_queue: asyncio.Queue,
    text_buffer: list,
    notion_service: NotionService,
    page_id: str,
    temp_dir: Path,
    summarized_chunks: list = None
):
    """
    Фоновый воркер, который транскрибирует чанки из очереди и суммаризирует их.
    
    Args:
        chunk_queue: Очередь с путями к аудио-файлам для транскрипции
        text_buffer: Список для накопления текста
        notion_service: Сервис Notion для дозаписи
        page_id: ID страницы Notion
        temp_dir: Директория для временных файлов
        summarized_chunks: Список для накопления суммаризированных чанков
    """
    from app.services.context_loader import ContextLoader
    from datetime import datetime
    
    chunk_counter = 0
    
    # Инициализируем сервисы для суммаризации
    context_loader = ContextLoader()
    ollama = OllamaService(context_loader=context_loader)
    
    # Предзагружаем контекст из Notion
    try:
        await context_loader.ensure_notion_sync()
        logger.info("✅ Контекст загружен для суммаризации чанков")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось загрузить контекст из Notion: {e}")
    
    if summarized_chunks is None:
        summarized_chunks = []
    
    while True:
        try:
            # Получаем путь к файлу из очереди
            audio_file = await chunk_queue.get()
            
            if audio_file is None:  # Сигнал остановки
                logger.info("🛑 Воркер транскрипции получил сигнал остановки")
                break
            
            chunk_counter += 1
            transcription_start = datetime.now()
            logger.info(f"📝 Транскрибируем чанк #{chunk_counter}...")
            
            # Транскрибируем с обработкой ошибок
            text = None
            try:
                text = await transcription_service.transcribe(audio_file)
                transcription_time = (datetime.now() - transcription_start).total_seconds()
                logger.info(f"⏱️ Транскрипция чанка #{chunk_counter} заняла {transcription_time:.2f} сек")
            except Exception as transcribe_error:
                transcription_time = (datetime.now() - transcription_start).total_seconds()
                logger.error(
                    f"❌ Ошибка транскрипции чанка #{chunk_counter}: {transcribe_error}\n"
                    f"   Тип ошибки: {type(transcribe_error).__name__}\n"
                    f"   Время до ошибки: {transcription_time:.2f} сек\n"
                    f"   Файл: {audio_file}"
                )
                # Продолжаем работу, не прерываем из-за ошибки транскрипции
                text = None
            
            if text:
                text_buffer.append(text)
                full_text = "\n\n".join(text_buffer)
                
                logger.info(f"✅ Чанк #{chunk_counter} транскрибирован ({len(text)} симв.)")
                
                # Суммаризируем чанк с контекстом
                summary = None
                summarization_start = datetime.now()
                try:
                    # Извлекаем сущности из текста
                    entities = await context_loader.resolve_entity(text, use_fuzzy=True, fuzzy_threshold=0.6)
                    projects = entities.get('projects', [])
                    people = entities.get('people', [])
                    terms = context_loader.find_glossary_terms(text)
                    
                    entities_count = len(projects) + len(people) + len(terms)
                    logger.info(
                        f"🔍 Чанк #{chunk_counter}: найдено сущностей - "
                        f"проекты: {len(projects)}, люди: {len(people)}, термины: {len(terms)} "
                        f"(всего: {entities_count})"
                    )
                    
                    # Суммаризируем с контекстом
                    summary = await ollama.summarize_chunk_with_context(
                        chunk_text=text,
                        chunk_number=chunk_counter,
                        projects=projects,
                        people=people,
                        terms=terms
                    )
                    
                    summarization_time = (datetime.now() - summarization_start).total_seconds()
                    summary_length = len(summary)
                    logger.info(
                        f"⏱️ Суммаризация чанка #{chunk_counter} завершена: "
                        f"время={summarization_time:.2f}сек, длина={summary_length} симв., "
                        f"сущностей={entities_count}"
                    )
                    
                    # Сохраняем суммаризированный чанк
                    summarized_chunks.append(summary)
                    
                except Exception as summary_error:
                    summarization_time = (datetime.now() - summarization_start).total_seconds()
                    logger.error(
                        f"❌ Ошибка суммаризации чанка #{chunk_counter}: {summary_error}\n"
                        f"   Тип ошибки: {type(summary_error).__name__}\n"
                        f"   Время до ошибки: {summarization_time:.2f} сек\n"
                        f"   Длина текста: {len(text)} символов\n"
                        f"   Найдено сущностей: {entities_count if 'entities_count' in locals() else 0}"
                    )
                    # Продолжаем работу, даже если суммаризация не удалась
                    summary = None
                    # Сохраняем сырой текст как fallback
                    if text:
                        summarized_chunks.append(text[:150] + "...")
                
                # Дозаписываем в Notion с обработкой ошибок
                try:
                    notion_content = f"\n\n[Чанк #{chunk_counter}]\n{text}"
                    if summary:
                        notion_content += f"\n\n📋 Саммари: {summary}"
                    
                    await notion_service.append_to_meeting(page_id, notion_content)
                    logger.info(f"✅ Чанк #{chunk_counter} добавлен в Notion" + (f" (с саммари)" if summary else ""))
                except Exception as e:
                    logger.error(f"❌ Ошибка при добавлении в Notion: {e}")
                    # Продолжаем работу, даже если не удалось записать в Notion
            else:
                logger.warning(f"⚠️ Чанк #{chunk_counter}: транскрипция вернула пустой текст или произошла ошибка")
            
            # Удаляем временный файл
            try:
                if os.path.exists(audio_file):
                    os.remove(audio_file)
            except Exception as e:
                logger.warning(f"⚠️ Не удалось удалить {audio_file}: {e}")
            
            chunk_queue.task_done()
            
        except asyncio.CancelledError:
            logger.info("🛑 Воркер транскрипции получил сигнал отмены")
            break
        except Exception as e:
            logger.error(f"❌ Ошибка в воркере транскрипции: {e}")
            # Продолжаем работу, не прерываем из-за ошибки
            try:
                chunk_queue.task_done()
            except:
                pass


async def main():
    """Главная функция для записи встречи."""
    logger.info("🚀 Запуск потоковой записи встречи")
    
    # Находим аудио-устройства
    mic_id, blackhole_id = find_audio_devices()
    
    if mic_id is None:
        logger.error("❌ Не найдено ни одного устройства ввода")
        return
    
    # Проверяем настройки
    settings = get_settings()
    page_id = settings.notion_meeting_page_id
    
    if not page_id:
        logger.error("❌ NOTION_MEETING_PAGE_ID не установлен в .env")
        return
    
    # Создаем директорию для временных файлов
    temp_dir = Path(project_root / "data" / "temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Устанавливаем флаг записи (чтобы NotionBackgroundParser не обрабатывал чанки как отдельные встречи)
    recording_flag_path = Path("/tmp/is_recording.flag")
    try:
        recording_flag_path.touch()
        logger.debug("Флаг is_recording установлен")
    except Exception as e:
        logger.warning(f"Не удалось установить флаг записи: {e}")
    
    # Инициализируем сервисы
    notion = NotionService()
    telegram = TelegramService()
    ollama = OllamaService()
    
    # Получаем или создаем страницу "AI Context" для хранения всех встреч
    meeting_start = datetime.now()
    meeting_title = f"Встреча {meeting_start.strftime('%Y-%m-%d %H:%M')}"
    
    try:
        # Получаем или создаем страницу "AI Context"
        ai_context_page_id = await notion.get_or_create_ai_context_page(parent_page_id=page_id)
        logger.info(f"✅ Используется страница AI Context: {ai_context_page_id}")
        
        # Создаем временную страницу для потоковой записи (для обратной совместимости)
        # Но финальный результат сохраним в AI Context
        meeting_page_id = await notion.create_meeting_page(
            meeting_title=meeting_title,
            summary="🎙 Запись начата...",
            participants=[],
            action_items=[],
            parent_page_id=page_id
        )
        logger.info(f"✅ Создана временная страница встречи: {meeting_page_id}")
        
        # Отправляем уведомление о начале
        await telegram.send_notification(
            f"<b>🎙 Начало записи встречи</b>\n\n"
            f"📄 AI Context: <code>{ai_context_page_id}</code>\n"
            f"⏰ Время: {meeting_start.strftime('%H:%M:%S')}"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка при создании страниц: {e}")
        meeting_page_id = page_id  # Fallback на основную страницу
        ai_context_page_id = page_id
    
    # Инициализируем рекордер
    recorder = ChunkedAudioRecorder(mic_id, blackhole_id)
    chunk_queue = asyncio.Queue()
    text_buffer = []
    summarized_chunks = []  # Список для накопления суммаризированных чанков
    
    # Запускаем воркер транскрипции
    worker_task = asyncio.create_task(
        transcription_worker(chunk_queue, text_buffer, notion, meeting_page_id, temp_dir, summarized_chunks)
    )
    
    # Начинаем запись
    print("\n" + "="*50)
    print("🎙 ЗАПИСЬ ВСТРЕЧИ НАЧАТА")
    print("="*50)
    print(f"📝 Транскрипция будет происходить каждые {CHUNK_DURATION} секунд")
    print("⏹ Нажмите ENTER, чтобы остановить запись и завершить встречу")
    print("="*50 + "\n")
    
    streams = await recorder.start_recording()
    
    # Создаем флаг для остановки
    stop_event = asyncio.Event()
    stop_flag_path = Path("/tmp/stop_recording.flag")
    
    # Обработчик сигналов
    def signal_handler():
        logger.info("⏹ Получен сигнал остановки (SIGTERM/SIGINT)")
        stop_event.set()
        
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    async def wait_for_enter():
        """Ждет нажатия Enter для остановки записи."""
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, sys.stdin.readline)
            logger.info("⏹ Получен сигнал остановки (Enter)")
            stop_event.set()
        except Exception:
            pass # Игнорируем ошибки stdin (например, если нет tty)
    
    # Запускаем задачу ожидания Enter (только если есть stdin)
    enter_task = None
    try:
        if sys.stdin.isatty():
            enter_task = asyncio.create_task(wait_for_enter())
    except Exception as e:
        logger.debug(f"Не удалось запустить задачу ожидания Enter: {e}")
    
    try:
        chunk_counter = 0
        last_chunk_time = datetime.now()
        
        # Основной цикл: каждые 30 секунд извлекаем чанк
        while not stop_event.is_set():
            # Проверяем файл-флаг
            if stop_flag_path.exists():
                logger.info("⏹ Обнаружен файл-флаг остановки")
                stop_event.set()
                # Удаляем флаг, чтобы не срабатывал повторно
                try:
                    stop_flag_path.unlink()
                except:
                    pass
                break

            # Ждем 1 секунду или сигнал остановки
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
                if stop_event.is_set():
                    break
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"Ошибка в цикле ожидания: {e}")
                # Продолжаем работу, не прерываем запись
                await asyncio.sleep(1)
                continue
            
            # Проверяем, пора ли извлекать чанк (каждые CHUNK_DURATION секунд)
            if (datetime.now() - last_chunk_time).total_seconds() >= CHUNK_DURATION:
                last_chunk_time = datetime.now()
                
                try:
                    # Извлекаем чанк
                    chunk = await recorder.extract_chunk()
                    
                    if chunk is None:
                        logger.warning("⚠️ Недостаточно данных для чанка, пропускаем")
                        continue
                    
                    chunk_counter += 1
                    chunk_file = temp_dir / f"chunk_{chunk_counter:03d}_{datetime.now().strftime('%H%M%S')}.wav"
                    
                    # Сохраняем чанк
                    recorder.save_chunk_to_wav(chunk, chunk_file)
                    logger.info(f"💾 Чанк #{chunk_counter} сохранен: {chunk_file.name}")
                    
                    # Отправляем в очередь на транскрипцию
                    await chunk_queue.put(str(chunk_file))
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке чанка #{chunk_counter}: {e}")
                    # Продолжаем запись, не прерываем из-за ошибки одного чанка
                    continue
            
    except KeyboardInterrupt:
        logger.info("⏹ Получен сигнал остановки (Ctrl+C)")
        stop_event.set()
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в основном цикле записи: {e}")
        stop_event.set()
    finally:
        # Останавливаем запись
        recorder.stop_recording(streams)
        
        # Ждем завершения всех транскрипций
        logger.info("⏳ Ожидание завершения транскрипций...")
        await chunk_queue.join()
        
        # Останавливаем воркер
        await chunk_queue.put(None)  # Сигнал остановки
        await worker_task
        
        # Формируем финальный текст
        full_transcript = "\n\n".join(text_buffer)
        meeting_end = datetime.now()
        duration = meeting_end - meeting_start
        
        logger.info(f"✅ Запись завершена. Длительность: {duration}")
        logger.info(f"📝 Всего транскрибировано: {len(full_transcript)} символов")
        logger.info(f"📋 Всего суммаризировано чанков: {len(summarized_chunks)}")
        
        # Сохраняем встречу в AI Context с полной структурой
        if full_transcript:
            # Определяем переменные заранее, чтобы они были доступны во всех блоках
            summary = None
            duration_str = str(duration).split('.')[0]  # Убираем микросекунды
            meeting_date_str = meeting_start.strftime('%Y-%m-%d %H:%M:%S')
            
            try:
                # Генерируем финальное саммари из суммаризированных чанков
                if summarized_chunks:
                    logger.info("🤖 Генерирую финальное саммари из суммаризированных чанков...")
                    summary = await ollama.summarize_from_chunks(summarized_chunks)
                else:
                    # Fallback: если не было суммаризированных чанков, используем обычную суммаризацию
                    logger.warning("⚠️ Нет суммаризированных чанков, использую обычную суммаризацию")
                    summary = await ollama.summarize_text(full_transcript, max_length=500)
            except Exception as e:
                logger.error(f"❌ Ошибка при генерации саммари: {e}")
                summary = "Не удалось сгенерировать саммари"
            
            try:
                # Сохраняем встречу в AI Context
                await notion.save_meeting_to_ai_context(
                    ai_context_page_id=ai_context_page_id,
                    meeting_title=meeting_title,
                    meeting_date=meeting_date_str,
                    summary=summary or "Саммари не сгенерировано",
                    full_transcript=full_transcript,
                    duration=duration_str,
                    participants=None  # Можно добавить извлечение участников из транскрипции
                )
                
                logger.info("✅ Встреча сохранена в AI Context")
            except Exception as e:
                logger.error(f"❌ Ошибка при сохранении в AI Context: {e}")
            
            try:
                # Также обновляем временную страницу для обратной совместимости
                # Добавляем маркер завершения перед саммари, чтобы NotionBackgroundParser понял, что встреча завершена
                await notion.append_to_meeting(
                    meeting_page_id,
                    f"\n\n---\n[MEETING_COMPLETE]\n## 📋 Саммари встречи\n{summary or 'Саммари не сгенерировано'}\n"
                )
                await notion.append_to_meeting(
                    meeting_page_id,
                    f"\n\n---\n## 📝 Полная транскрипция ({duration_str})\n{full_transcript}"
                )
                logger.info("✅ Временная страница обновлена")
            except Exception as e:
                logger.error(f"❌ Ошибка при обновлении временной страницы: {e}")
            
            try:
                # Отправляем финальное уведомление с саммари
                await telegram.send_notification(
                    f"<b>✅ Запись встречи завершена</b>\n\n"
                    f"⏰ Длительность: {duration_str}\n"
                    f"📝 Символов: {len(full_transcript)}\n\n"
                    f"<b>📋 Саммари:</b>\n{summary or 'Не удалось сгенерировать'}\n\n"
                    f"📄 AI Context: <code>{ai_context_page_id}</code>"
                )
                logger.info("✅ Финальное уведомление отправлено")
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке финального уведомления: {e}")
                # В случае ошибки все равно отправляем базовое уведомление
                try:
                    await telegram.send_notification(
                        f"<b>✅ Запись завершена</b>\n\n"
                        f"⏰ Длительность: {duration_str}\n"
                        f"📝 Символов: {len(full_transcript)}\n"
                        f"⚠️ Ошибка при генерации саммари"
                    )
                except:
                    pass
            
            logger.info("✅ Встреча успешно завершена")
        
        # Снимаем флаг записи (чтобы NotionBackgroundParser мог обработать завершенную встречу)
        try:
            if recording_flag_path.exists():
                recording_flag_path.unlink()
                logger.debug("Флаг is_recording снят")
        except Exception as e:
            logger.warning(f"Не удалось снять флаг записи: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
