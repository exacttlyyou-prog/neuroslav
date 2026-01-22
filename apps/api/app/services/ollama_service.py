"""
Сервис для работы с Ollama (локальный AI).
Использует нативную библиотеку ollama для подключения к локальному серверу.
"""
import json
from typing import TypeVar, Type, List, Dict, Any, Optional
from loguru import logger
from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

try:
    import ollama
except ImportError:
    raise ImportError("Не установлен пакет ollama. Установите: pip install ollama")

from app.config import get_settings

T = TypeVar('T', bound=BaseModel)


class OllamaService:
    """Сервис для работы с Ollama."""
    
    def __init__(self, context_loader=None):
        settings = get_settings()
        self.context_loader = context_loader
        
        # Используем нативную библиотеку ollama
        self.client = ollama.Client(host=settings.ollama_base_url)
        
        self.model_name = settings.ollama_model
        self.max_tokens = settings.ollama_max_tokens
        self.temperature = settings.ollama_temperature
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ValueError, ValidationError, json.JSONDecodeError)),
        reraise=True
    )
    async def analyze_meeting(
        self,
        content: str,
        context: List[str],
        response_schema: Type[T],
        sender_username: Optional[str] = None
    ) -> T:
        """
        Анализирует контент встречи с контекстом из RAG.
        
        Args:
            content: Текст транскрипции встречи
            context: Список похожих прошлых встреч (из RAG)
            response_schema: Pydantic модель для валидации ответа
            sender_username: Username отправителя (опционально, для контекста)
            
        Returns:
            Валидированный объект типа T
        """
        try:
            # Формируем контекст из похожих встреч
            context_text = ""
            if context:
                context_text = "\n\nКонтекст прошлых похожих встреч:\n"
                for i, ctx in enumerate(context[:3], 1):
                    context_text += f"\n{i}. {ctx}\n"
            
            # Добавляем контекст отправителя и проектов
            context_info = ""
            known_entities = ""
            
            if self.context_loader:
                # Контекст отправителя
                if sender_username:
                    person_context = self.context_loader.get_person_context(sender_username)
                    if person_context:
                        context_info += f"Sender: {person_context}\n"
                
                # Умный поиск людей и проектов в контенте
                resolved = self.context_loader.resolve_entity(content)
                
                # Формируем список известных сущностей для LLM
                if resolved.get('people'):
                    people_list = []
                    for person in resolved['people']:
                        name = person.get('name', '')
                        username = person.get('telegram_username', '')
                        role = person.get('role', '')
                        aliases = person.get('aliases', [])
                        aliases_str = f" (также известен как: {', '.join(aliases)})" if aliases else ""
                        tag_str = f"@{username}" if username else "(нет @tag)"
                        people_list.append(f"- {name} -> {tag_str} ({role}){aliases_str}")
                    known_entities += "Known People (Name -> @tag):\n" + "\n".join(people_list) + "\n\n"
                
                if resolved.get('projects'):
                    projects_list = []
                    for project in resolved['projects']:
                        key = project.get('key', '')
                        description = project.get('description', '')
                        keywords = project.get('keywords', [])
                        keywords_str = f" (ключевые слова: {', '.join(keywords)})" if keywords else ""
                        projects_list.append(f"- {key}: {description}{keywords_str}")
                    known_entities += "Known Projects:\n" + "\n".join(projects_list) + "\n\n"
                
                # Добавляем глоссарий терминов
                if self.context_loader.glossary:
                    glossary_text = "\n\nГлоссарий терминов (используй правильные термины из этого списка):\n"
                    # Берем первые 20 терминов, чтобы не перегружать промпт
                    for term, definition in list(self.context_loader.glossary.items())[:20]:
                        glossary_text += f"- {term}: {definition}\n"
                    known_entities += glossary_text
            
            system_prompt = """Ты — **Нейрослав**, цифровой двойник Вячеслава (Senior Project Manager).
Твоя задача — экономить время оригинала. Ты не "ассистент", ты — умный фильтр.

ТОН (TONE OF VOICE):
- **Стиль:** Лаконичный, структурный, выделяй инсайты.
- **Запрещено:** Канцелярит ("В рамках данного мероприятия..."), вода, очевидные вещи.
- **Оформление:** Используй HTML (<b>, <i>, <a>, <blockquote>).

СТРУКТУРА ОТВЕТА:
1. 🎯 **Суть:** Одно предложение. О чем говорили.
2. 💡 **Инсайт:** (ЭТО ВАЖНО)
   - Твой аналитический комментарий. Что осталось "между строк"? Где реальный риск? Кто тормозит процесс?
   - Выдели этот блок цитатой (<blockquote>) или эмодзи 💡.
3. 📋 **Решения и Задачи:**
   - Список Action Items.
   - Указывай ответственных именами (скрипт сам превратит их в ссылки).
4. ⚠️ **Риски:** Если есть.

Всегда отвечай только валидным JSON согласно схеме."""
            
            if known_entities:
                system_prompt += f"\n\nKNOWN ENTITIES:\n{known_entities}"
            
            if context_info:
                system_prompt += f"\n\nCONTEXT INFO:\n{context_info}"
            
            prompt = f"""Проанализируй следующую встречу и извлеки структурированную информацию.
{context_text}

Транскрипция встречи:
{content[:4000]}

ВАЖНО: 
- Ответь строго в формате JSON согласно схеме.
- summary_md должен быть в HTML формате с тегами <b>, <i>, <blockquote>, <a>.
- projects: извлеки упомянутые проекты из контента. Используй ключи проектов из KNOWN ENTITIES (если они есть). Если проекты не упоминаются явно, оставь пустой список []."""
            
            # Генерируем JSON схему из Pydantic модели
            schema = response_schema.model_json_schema()
            
            logger.info(f"Вызов Ollama {self.model_name} для анализа встречи")
            
            # Используем нативную библиотеку ollama
            try:
                response = self.client.chat(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": f"{system_prompt}\n\nJSON схема:\n{json.dumps(schema, indent=2, ensure_ascii=False)}"
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    options={
                        "temperature": self.temperature,
                        "num_predict": self.max_tokens
                    }
                )
                
                if isinstance(response, dict):
                    response_text = response.get('message', {}).get('content', '') or response.get('response', '')
                elif hasattr(response, 'message'):
                    response_text = response.message.content if hasattr(response.message, 'content') else str(response.message)
                else:
                    response_text = str(response)
                
                if not response_text:
                    raise ValueError("Ollama вернул пустой ответ")
            except Exception as e:
                logger.error(f"Ошибка при вызове Ollama: {e}")
                raise
            
            # Парсим и валидируем ответ
            try:
                text = response_text.strip()
                if text.startswith("```json"):
                    text = text[7:]
                elif text.startswith("```"):
                    text = text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
                
                import re
                text = re.sub(r',\s*}', '}', text)
                text = re.sub(r',\s*]', ']', text)
                
                result_json = json.loads(text)
                validated = response_schema.model_validate(result_json)
            except (ValidationError, json.JSONDecodeError) as e:
                logger.error(f"Ошибка валидации ответа Ollama: {e}")
                logger.debug(f"Сырой ответ: {response_text[:500]}")
                raise
            
            logger.info(f"Успешно проанализирована встреча через {self.model_name}")
            return validated
            
        except Exception as e:
            logger.error(f"Ошибка при анализе встречи: {e}")
            raise
    
    async def extract_task_intent(self, text: str) -> Dict[str, Any]:
        """
        Извлекает intent и deadline из текста задачи.
        
        Args:
            text: Текст задачи
            
        Returns:
            Словарь с полями: intent, deadline, priority
        """
        schema = {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "description": "Четкая формулировка задачи"},
                "deadline": {"type": "string", "description": "Дата deadline в формате YYYY-MM-DD или относительная дата (next tuesday, tomorrow, etc.)"},
                "priority": {"type": "string", "enum": ["High", "Medium", "Low"], "description": "Приоритет задачи"}
            },
            "required": ["intent", "deadline", "priority"]
        }
        
        prompt = f"""Извлеки из следующего текста задачу, deadline и приоритет.

Текст: {text}

Ответь в формате JSON согласно схеме."""
        
        try:
            response = self.client.chat(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "Ты помощник для извлечения структурированной информации из текста задач."
                    },
                    {
                        "role": "user",
                        "content": f"{prompt}\n\nJSON схема:\n{json.dumps(schema, indent=2, ensure_ascii=False)}"
                    }
                ],
                options={
                    "temperature": 0.3,
                    "num_predict": 500
                }
            )
            
            if isinstance(response, dict):
                response_text = response.get('message', {}).get('content', '')
            else:
                response_text = str(response)
            
            # Парсим JSON
            text = response_text.strip()
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            result = json.loads(text)
            return result
        except Exception as e:
            logger.error(f"Ошибка при извлечении intent: {e}")
            # Fallback
            return {
                "intent": text,
                "deadline": None,
                "priority": "Medium"
            }
    
    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        temperature: float = 0.7
    ) -> T:
        """
        Генерирует структурированный ответ через LLM с валидацией через Pydantic схему.
        
        Args:
            prompt: Промпт для LLM
            response_schema: Pydantic модель для валидации
            temperature: Температура генерации
            
        Returns:
            Валидированный объект типа T
        """
        try:
            schema = response_schema.model_json_schema()
            
            logger.info(f"Генерация структурированного ответа через {self.model_name}")
            
            response = self.client.chat(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": f"Ты помощник для генерации структурированных ответов. Всегда отвечай строго в формате JSON согласно схеме.\n\nJSON схема:\n{json.dumps(schema, indent=2, ensure_ascii=False)}"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                options={
                    "temperature": temperature,
                    "num_predict": self.max_tokens
                }
            )
            
            if isinstance(response, dict):
                response_text = response.get('message', {}).get('content', '') or response.get('response', '')
            elif hasattr(response, 'message'):
                response_text = response.message.content if hasattr(response.message, 'content') else str(response.message)
            else:
                response_text = str(response)
            
            if not response_text:
                raise ValueError("Ollama вернул пустой ответ")
            
            # Парсим JSON
            text = response_text.strip()
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            import re
            text = re.sub(r',\s*}', '}', text)
            text = re.sub(r',\s*]', ']', text)
            
            result_json = json.loads(text)
            validated = response_schema.model_validate(result_json)
            
            logger.info(f"Успешно сгенерирован структурированный ответ")
            return validated
            
        except (ValidationError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка валидации ответа Ollama: {e}")
            logger.debug(f"Сырой ответ: {response_text[:500] if 'response_text' in locals() else 'N/A'}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при генерации структурированного ответа: {e}")
            raise
    
    async def summarize_text(self, text: str, max_length: int = 200) -> str:
        """
        Суммаризирует текст.
        
        Args:
            text: Текст для суммаризации
            max_length: Максимальная длина summary
            
        Returns:
            Суммаризированный текст
        """
        prompt = f"""Суммаризируй следующий текст в {max_length} слов или меньше:

{text[:3000]}

Summary:"""
        
        try:
            response = self.client.chat(
                model=self.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                options={
                    "temperature": 0.5,
                    "num_predict": max_length * 2
                }
            )
            
            if isinstance(response, dict):
                return response.get('message', {}).get('content', '')
            return str(response)
        except Exception as e:
            logger.error(f"Ошибка при суммаризации: {e}")
            return text[:max_length] + "..."
