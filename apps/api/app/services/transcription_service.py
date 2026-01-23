import os
import whisper
import asyncio
import torch
from pathlib import Path
from loguru import logger
from typing import Optional, Union

class TranscriptionService:
    """
    Сервис для локальной транскрипции аудио с использованием OpenAI Whisper.
    Оптимизировано для Apple Silicon (Metal).
    """
    
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TranscriptionService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Определяем устройство для вычислений
        if torch.backends.mps.is_available():
            self.device = "mps" # Apple Silicon GPU
            logger.info("🚀 Whisper будет использовать Apple Silicon GPU (MPS)")
        elif torch.cuda.is_available():
            self.device = "cuda"
            logger.info("🚀 Whisper будет использовать NVIDIA GPU (CUDA)")
        else:
            self.device = "cpu"
            logger.info("ℹ️ Whisper будет использовать CPU")

    async def _get_model(self):
        """Ленивая загрузка модели."""
        if self._model is None:
            logger.info("📥 Загрузка модели Whisper (small)...")
            # Загружаем модель в отдельном потоке, чтобы не блокировать event loop
            self._model = await asyncio.to_thread(whisper.load_model, "small", device=self.device)
            logger.info("✅ Модель Whisper загружена")
        return self._model

    async def transcribe(self, audio_path: Union[str, Path], language: str = "ru") -> Optional[str]:
        """
        Транскрибирует аудиофайл в текст.
        
        Args:
            audio_path: Путь к аудиофайлу (.wav, .mp3, etc)
            language: Язык (по умолчанию русский)
            
        Returns:
            Текст транскрипции или None в случае ошибки
        """
        try:
            model = await self._get_model()
            audio_path = str(audio_path)
            
            if not os.path.exists(audio_path):
                logger.error(f"❌ Файл не найден: {audio_path}")
                return None

            logger.info(f"🎙 Начало транскрипции файла: {audio_path}...")
            
            # Запускаем транскрипцию в отдельном потоке
            # Отключаем fp16 для MPS, так как это вызывает ошибки (NaN)
            use_fp16 = (self.device == "cuda")
            
            result = await asyncio.to_thread(
                model.transcribe, 
                audio_path, 
                language=language,
                fp16=use_fp16
            )
            
            text = result.get("text", "").strip()
            logger.info(f"✅ Транскрипция завершена ({len(text)} симв.)")
            return text

        except Exception as e:
            logger.error(f"❌ Ошибка при транскрипции: {e}")
            return None

# Singleton instance
transcription_service = TranscriptionService()
