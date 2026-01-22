"""
Клиент для работы с Google Gemini 3.0 Flash через Native Structured Outputs.
"""
import json
from typing import TypeVar, Type
from google import genai
from google.genai.types import GenerateContentConfig, HttpOptions
from loguru import logger
from pydantic import BaseModel, ValidationError

from core.config import get_settings

T = TypeVar('T', bound=BaseModel)


class GeminiClient:
    """Клиент для работы с Gemini 3.0 Flash."""
    
    def __init__(self):
        settings = get_settings()
        if settings.use_vertex_ai:
            # TODO: Реализовать через Vertex AI если нужно
            raise NotImplementedError("Vertex AI пока не реализован")
        else:
            self.client = genai.Client(
                api_key=settings.gemini_api_key,
                http_options=HttpOptions(api_version="v1")
            )
            self.model = settings.gemini_model
    
    async def analyze_meeting(
        self,
        content: str,
        response_schema: Type[T]
    ) -> T:
        """
        Анализирует контент встречи и возвращает структурированный результат.
        
        Args:
            content: Текст встречи из Notion
            response_schema: Pydantic модель для валидации ответа
            
        Returns:
            Валидированный объект типа T
        """
        try:
            # Используем Native Structured Outputs через response_json_schema
            prompt = f"""Проанализируй следующую встречу и извлеки:
1. Краткое саммари в Markdown
2. Список задач (action items) с приоритетами и ответственными
3. Предложенную дату встречи (если упоминается)
4. Оценку рисков (если есть)

Контент встречи:
{content}
"""
            
            # Генерируем JSON схему из Pydantic модели
            schema = response_schema.model_json_schema()
            
            # Конфигурация с structured outputs
            config = GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=schema,
                max_output_tokens=2048
            )
            
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config
            )
            
            # Проверяем, что ответ не пустой
            if response.text is None:
                logger.error("Gemini вернул пустой ответ (возможно, превышен max_output_tokens)")
                raise ValueError("Empty response from Gemini")
            
            # Парсим и валидируем ответ
            try:
                result_json = json.loads(response.text)
                validated = response_schema.model_validate(result_json)
            except ValidationError as e:
                logger.error(f"Ошибка валидации ответа Gemini: {e}")
                logger.debug(f"Сырой ответ: {response.text}")
                raise
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON от Gemini: {e}")
                logger.debug(f"Сырой ответ: {response.text}")
                raise
            
            logger.info(f"Успешно проанализирована встреча, извлечено {len(validated.action_items)} задач")
            return validated
            
        except Exception as e:
            logger.error(f"Ошибка при анализе встречи: {e}")
            raise

