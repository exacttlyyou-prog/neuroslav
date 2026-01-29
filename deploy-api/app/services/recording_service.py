"""
Сервис для управления записью встреч.
"""
import subprocess
import os
import signal
from pathlib import Path
from typing import Optional
from loguru import logger

from app.config import get_settings


class RecordingService:
    """Сервис для управления процессом записи встреч."""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.script_path = Path(__file__).parent.parent.parent / "scripts" / "record_meeting.py"
        self.stop_flag_path = Path("/tmp/stop_recording.flag")
    
    def is_recording(self) -> bool:
        """Проверяет, идет ли запись."""
        if self.process is None:
            return False
        
        # Проверяем, жив ли процесс
        if self.process.poll() is not None:
            # Процесс завершился
            self.process = None
            return False
        
        return True
    
    def start_recording(self) -> bool:
        """
        Запускает запись встречи.
        
        Returns:
            True если запись запущена, False если уже идет
        """
        if self.is_recording():
            logger.warning("Запись уже идет")
            return False
        
        try:
            # Удаляем флаг остановки, если есть
            if self.stop_flag_path.exists():
                self.stop_flag_path.unlink()
            
            # Устанавливаем глобальный флаг записи (для NotionBackgroundParser)
            # Примечание: флаг также устанавливается в record_meeting.py, но здесь устанавливаем для надежности
            try:
                recording_flag_path = Path("/tmp/is_recording.flag")
                recording_flag_path.touch()
                logger.debug("Флаг is_recording установлен в recording_service")
            except Exception as e:
                logger.warning(f"Не удалось установить глобальный флаг записи: {e}")
            
            # Запускаем скрипт записи
            settings = get_settings()
            env = os.environ.copy()
            
            # Устанавливаем переменные окружения из настроек
            if settings.notion_token:
                env["NOTION_TOKEN"] = settings.notion_token
            if getattr(settings, "notion_ai_context_page_id", None):
                env["NOTION_AI_CONTEXT_PAGE_ID"] = settings.notion_ai_context_page_id
            if settings.notion_meeting_page_id:
                env["NOTION_MEETING_PAGE_ID"] = settings.notion_meeting_page_id
            if settings.telegram_bot_token:
                env["TELEGRAM_BOT_TOKEN"] = settings.telegram_bot_token
            if settings.admin_chat_id:
                env["ADMIN_CHAT_ID"] = settings.admin_chat_id
            if settings.ollama_base_url:
                env["OLLAMA_BASE_URL"] = settings.ollama_base_url
            if settings.ollama_model:
                env["OLLAMA_MODEL"] = settings.ollama_model
            
            # Запускаем процесс в фоне
            log_file = open("/tmp/record_meeting.log", "w")
            self.process = subprocess.Popen(
                ["python", str(self.script_path)],
                cwd=str(self.script_path.parent.parent),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True  # Создаем новую сессию, чтобы процесс не зависел от родителя
            )
            
            logger.info(f"Запись встречи запущена (PID: {self.process.pid})")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при запуске записи: {e}")
            self.process = None
            return False
    
    async def stop_recording(self) -> bool:
        """
        Останавливает запись встречи.
        
        Returns:
            True если запись остановлена, False если не было запущено
        """
        if not self.is_recording():
            logger.warning("Запись не запущена")
            return False
        
        try:
            # Создаем флаг остановки
            self.stop_flag_path.touch()
            
            # Отправляем сигнал SIGTERM процессу
            if self.process:
                try:
                    # Проверяем, что процесс еще жив
                    if self.process.poll() is not None:
                        logger.info("Процесс уже завершился")
                        self.process = None
                        # Снимаем глобальный флаг записи
                        try:
                            recording_flag_path = Path("/tmp/is_recording.flag")
                            if recording_flag_path.exists():
                                recording_flag_path.unlink()
                                logger.debug("Флаг is_recording снят")
                        except Exception as e:
                            logger.debug(f"Не удалось снять глобальный флаг: {e}")
                        return True
                    
                    # Пробуем мягко остановить
                    logger.info(f"Отправляю SIGTERM процессу {self.process.pid}")
                    self.process.terminate()
                    
                    # Ждем до 60 секунд в отдельном потоке, чтобы не блокировать event loop
                    import asyncio
                    try:
                        await asyncio.to_thread(self.process.wait, timeout=60)
                    except subprocess.TimeoutExpired:
                        # Если не остановился, убиваем принудительно
                        logger.warning("Процесс не остановился за 60 секунд, принудительное завершение")
                        if self.process.poll() is None:  # Проверяем, что процесс еще жив
                            self.process.kill()
                            await asyncio.to_thread(self.process.wait)
                    
                    logger.info("Запись остановлена")
                    self.process = None
                    
                    # Снимаем глобальный флаг записи
                    try:
                        recording_flag_path = Path("/tmp/is_recording.flag")
                        if recording_flag_path.exists():
                            recording_flag_path.unlink()
                            logger.debug("Флаг is_recording снят")
                    except Exception as e:
                        logger.debug(f"Не удалось снять глобальный флаг: {e}")
                    
                    return True
                    
                except ProcessLookupError:
                    # Процесс уже завершился
                    logger.info("Процесс уже завершился")
                    self.process = None
                    
                    # Снимаем глобальный флаг записи
                    try:
                        recording_flag_path = Path("/tmp/is_recording.flag")
                        if recording_flag_path.exists():
                            recording_flag_path.unlink()
                    except Exception:
                        pass
                    
                    return True
                except Exception as e:
                    logger.error(f"Ошибка при остановке процесса: {e}")
                    self.process = None
                    
                    # Снимаем глобальный флаг записи
                    try:
                        recording_flag_path = Path("/tmp/is_recording.flag")
                        if recording_flag_path.exists():
                            recording_flag_path.unlink()
                    except Exception:
                        pass
                    
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при остановке записи: {e}")
            # В случае ошибки все равно пытаемся снять флаг
            try:
                recording_flag_path = Path("/tmp/is_recording.flag")
                if recording_flag_path.exists():
                    recording_flag_path.unlink()
                    logger.debug("Флаг is_recording снят после ошибки")
            except Exception:
                pass
            return False
    
    def get_status(self) -> dict:
        """
        Возвращает статус записи.
        
        Returns:
            Словарь с информацией о статусе
        """
        is_recording = self.is_recording()
        
        return {
            "is_recording": is_recording,
            "pid": self.process.pid if self.process and is_recording else None
        }


# Глобальный экземпляр сервиса
_recording_service: Optional[RecordingService] = None


def get_recording_service() -> RecordingService:
    """Получает глобальный экземпляр сервиса записи."""
    global _recording_service
    if _recording_service is None:
        _recording_service = RecordingService()
    return _recording_service
