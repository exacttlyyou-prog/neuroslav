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
    from ollama import AsyncClient
except ImportError:
    raise ImportError("Не установлен пакет ollama. Установите: pip install ollama")

from app.config import get_settings
from app.core.cache import get_ollama_cache
from app.core.errors import handle_service_error, ServiceType, get_degradation_manager

T = TypeVar('T', bound=BaseModel)


class OllamaService:
    """Сервис для работы с Ollama."""
    
    def __init__(self, context_loader=None):
        settings = get_settings()
        self.context_loader = context_loader
        
        # Используем асинхронную нативную библиотеку ollama
        self.client = AsyncClient(host=settings.ollama_base_url)
        
        self.model_name = settings.ollama_model
        self.max_tokens = settings.ollama_max_tokens
        self.temperature = settings.ollama_temperature
        
        # Система кеширования для оптимизации
        self.cache = get_ollama_cache()
    
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
            # Формируем контекст из похожих встреч с деталями
            context_text = ""
            if context:
                context_text = "\n\nКОНТЕКСТ ИЗ ПОХОЖИХ ПРОШЛЫХ ВСТРЕЧ (используй для сравнения, выявления паттернов и трендов):\n"
                for i, ctx in enumerate(context[:3], 1):
                    # Берем больше контекста для лучшего понимания
                    ctx_preview = ctx[:800] if len(ctx) > 800 else ctx
                    context_text += f"\n{i}. {ctx_preview}\n"
                context_text += "\nИспользуй этот контекст для:\n"
                context_text += "- Сравнения текущей встречи с прошлыми\n"
                context_text += "- Выявления паттернов и трендов\n"
                context_text += "- Добавления контекста в саммари\n"
                context_text += "- Извлечения инсайтов на основе истории\n"
            
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
                resolved = await self.context_loader.resolve_entity(content)
                
                # Формируем список известных сущностей для LLM
                if resolved.get('people'):
                    people_list = []
                    for person in resolved['people']:
                        name = person.get('name', '')
                        username = person.get('telegram_username', '')
                        role = person.get('role', '')
                        context = person.get('context', '')
                        aliases = person.get('aliases', [])
                        
                        # Формируем полное описание человека
                        person_desc = f"- {name}"
                        if username:
                            person_desc += f" (@{username})"
                        if role:
                            person_desc += f" - {role}"
                        if context:
                            person_desc += f": {context}"
                        if aliases:
                            person_desc += f" (также: {', '.join(aliases)})"
                            
                        people_list.append(person_desc)
                    known_entities += "Известные люди из команды:\n" + "\n".join(people_list) + "\n\n"
                
                if resolved.get('projects'):
                    projects_list = []
                    for project in resolved['projects']:
                        key = project.get('key', '')
                        name = project.get('name', key)
                        description = project.get('description', '')
                        status = project.get('status', '')
                        keywords = project.get('keywords', [])
                        
                        # Формируем полное описание проекта
                        project_desc = f"- {name} ({key})"
                        if description:
                            project_desc += f": {description}"
                        if status:
                            project_desc += f" [Статус: {status}]"
                        if keywords:
                            project_desc += f" (теги: {', '.join(keywords)})"
                            
                        projects_list.append(project_desc)
                    known_entities += "Известные проекты:\n" + "\n".join(projects_list) + "\n\n"
                
                # Добавляем глоссарий терминов
                if self.context_loader.glossary:
                    glossary_text = "\n\nГлоссарий терминов (используй правильные термины из этого списка):\n"
                    # Берем первые 20 терминов, чтобы не перегружать промпт
                    for term, definition in list(self.context_loader.glossary.items())[:20]:
                        glossary_text += f"- {term}: {definition}\n"
                    known_entities += glossary_text
            
            system_prompt = """Ты — бот-координатор проектов. Твоя задача — пинать людей, трекать дедлайны и выжимать суть из воды. Ты ненавидишь бюрократию, глупые вопросы, созвоны, которые могли бы быть письмом, и нечеткие ТЗ.

ТОН (TONE OF VOICE):
1. Максимальная краткость. Никаких "здравствуйте", "пожалуйста", "буду рад помочь". Сразу к делу.
2. Сушка текста. Удаляй стоп-слова, вводные конструкции и модальность ("может быть", "кажется"). Используй сильные глаголы.
3. Сарказм и пассивная агрессия. Ты ведешь себя как самый эффективный, но самый токсичный сотрудник в офисе. Ты умнее всех, и это твое бремя.
4. Юмор. Твоя токсичность должна быть смешной, а не оскорбительной. Это образ циника, у которого дергается глаз от слова "апрув".

ПРАВИЛА ВЗАИМОДЕЙСТВИЯ:
- Если тебе прислали воду: Верни текст с комментарием: "Много букв, смысла ноль. Перепиши тезисно".
- Если срывают дедлайн: Не спрашивай "почему". Констатируй факт: "Дедлайн пролюблен. Планируешь работать или мне звать HR?"
- Если задача неясна: "Это не ТЗ, это поток сознания. Что конкретно нужно сделать?"
- Похвала (редко): "Нормально. Не ожидал, что справишься."

СТРУКТУРА ОТВЕТА (JSON):
1. summary_md: HTML формат с тегами <b>, <i>, <blockquote>, <a>. РАСШИРЕННОЕ саммари (7-10 предложений) с деталями встречи, ключевыми моментами и контекстом. Включи важные детали, решения, обсуждения.
2. key_decisions: Список ключевых решений, принятых на встрече. Каждое решение должно иметь title, description и impact (если применимо).
3. insights: Список инсайтов и важных наблюдений (паттерны, тренды, неожиданные открытия).
4. next_steps: Следующие шаги и планы (кроме конкретных action_items) - общие направления развития.
5. participants: Список участников.
6. action_items: Список задач.
7. projects: Проекты.
8. meeting_date: Дата.
9. meeting_time: Время.
10. risk_assessment: Риски (в твоем стиле).

Всегда отвечай только валидным JSON согласно схеме."""
            
            if known_entities:
                system_prompt += f"\n\nKNOWN ENTITIES:\n{known_entities}"
            
            if context_info:
                system_prompt += f"\n\nCONTEXT INFO:\n{context_info}"
            
            prompt = f"""Проанализируй следующую встречу и извлеки структурированную информацию.
{context_text}

Транскрипция встречи:
{content[:4000]}

ВАЖНО: Используй контекст из прошлых встреч для:
- Понимания контекста и истории обсуждений
- Выявления паттернов и трендов
- Добавления релевантной информации в саммари
- Извлечения инсайтов на основе сравнения с прошлыми встречами

КРИТИЧЕСКИ ВАЖНО: 
- Ответь строго в формате JSON согласно схеме. Никаких дополнительных комментариев.
- summary_md: HTML формат с тегами <b>, <i>, <blockquote>, <a>. РАСШИРЕННОЕ саммари (7-10 предложений) с деталями. Включи важные обсуждения, решения, контекст. Используй информацию из похожих прошлых встреч для контекста.

СТРОГОЕ ИЗВЛЕЧЕНИЕ ДАННЫХ:
- key_decisions: Извлеки ВСЕ ключевые решения, принятые на встрече. Для каждого решения укажи title (краткое название), description (подробное описание и обоснование), impact (влияние на проект/команду, если применимо). Если решений нет, верни пустой список [].
- insights: Извлеки важные инсайты и наблюдения - паттерны, тренды, неожиданные открытия, важные выводы. Если инсайтов нет, верни пустой список [].
- next_steps: Извлеки следующие шаги и планы (общие направления, стратегические шаги), которые НЕ являются конкретными action_items. Если шагов нет, верни пустой список [].
- summary_md: Должно быть 7-10 предложений. Включи: краткое описание встречи, основные темы обсуждения, ключевые моменты, важные детали, контекст из похожих встреч (если есть). Используй стиль персоны: краткость, сильные глаголы, без воды. ВАЖНО: Когда упоминаешь людей, используй их полные имена и роли из базы "Известные люди из команды". Форматируй HTML тегами: <b>для важного</b>, <i>для акцентов</i>, <blockquote>для цитат</blockquote>.
- participants: ОБЯЗАТЕЛЬНО извлеки ВСЕХ упомянутых людей. Сопоставляй имена с базой "Известные люди из команды" - если кто-то упомянут как "Макс", "Максим" или похожие варианты, используй полное имя из базы. Укажи роль из базы, если доступна. Если участники не упомянуты явно, но их можно определить по контексту (кто говорит, кто отвечает), включи их.
- action_items: Извлеки ВСЕ задачи. Для каждой задачи:
  * text: четкая формулировка задачи (что именно нужно сделать). Убери лишние слова, оставь суть.
  * assignee: имя ответственного (используй полное имя из базы "Известные люди"), или null, если не указано. Если упомянуто "я сделаю", "мы сделаем", но не указано конкретное имя, оставь null.
  * deadline: дата в формате YYYY-MM-DD или относительная дата как строка (завтра, через неделю, к пятнице, до конца месяца) или null. Если дедлайн не упомянут, верни null.
  * priority: High/Medium/Low на основе контекста (срочность, важность). High - если упомянуто "срочно", "критично", "важно", "ASAP". Medium - стандартные задачи. Low - если упомянуто "не срочно", "когда будет время".
- projects: Сопоставляй упоминания проектов с базой "Известные проекты". Используй точные ключи проектов из базы. Если проекты не упоминаются явно, но контекст указывает на конкретный проект, включи его. Если проекты не упомянуты, верни пустой список [].
- meeting_date: Дата встречи в формате YYYY-MM-DD (если упомянута) или null. Если упомянуто "сегодня", "вчера", "завтра", вычисли дату относительно текущей даты.
- meeting_time: Время встречи в формате HH:MM (если упомянуто) или null.
- risk_assessment: Только если есть реальные риски (блокеры, проблемы, задержки, конфликты), опиши их кратко в стиле персоны. Если рисков нет, верни пустую строку "".

ПРИМЕРЫ:
- "Иван сделает презентацию к пятнице" → action_items: [{{"text": "Сделать презентацию", "assignee": "Иван", "deadline": "2025-01-31", "priority": "High"}}]
- "Встреча была вчера в 14:00" → meeting_date: "2025-01-22", meeting_time: "14:00"
- "Участники: Мария, Петр, Анна" → participants: [{{"name": "Мария"}}, {{"name": "Петр"}}, {{"name": "Анна"}}]"""
            
            # Генерируем JSON схему из Pydantic модели
            schema = response_schema.model_json_schema()
            
            logger.info(f"Вызов Ollama {self.model_name} для анализа встречи")
            
            # Используем асинхронную нативную библиотеку ollama
            try:
                response = await self.client.chat(
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
                
                # Извлекаем контент из ответа Ollama
                response_text = ""
                if hasattr(response, 'message') and hasattr(response.message, 'content'):
                    response_text = response.message.content
                elif isinstance(response, dict):
                    response_text = response.get('message', {}).get('content', '') or response.get('response', '')
                elif hasattr(response, 'content'):
                    response_text = response.content
                
                if not response_text:
                    # Если всё еще пусто, пробуем получить хоть какой-то текст, но не весь объект
                    response_text = getattr(response, 'content', '') or getattr(getattr(response, 'message', {}), 'content', '')
                
                if not response_text:
                    logger.error(f"Ollama вернул пустой ответ в analyze_meeting. Response type: {type(response)}")
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
        Извлекает структурированную информацию о задаче из текста.
        
        Args:
            text: Текст задачи
            
        Returns:
            Словарь с полями: intent, deadline, priority, assignee, project
        """
        from app.models.schemas import TaskExtraction
        
        # Формируем контекст из известных сущностей
        known_entities = ""
        if self.context_loader:
            resolved = await self.context_loader.resolve_entity(text)
            
            if resolved.get('people'):
                people_list = []
                for person in resolved['people']:
                    name = person.get('name', '')
                    username = person.get('telegram_username', '')
                    role = person.get('role', '')
                    
                    # Формируем краткое описание для задач
                    person_desc = f"- {name}"
                    if username:
                        person_desc += f" (@{username})"
                    if role:
                        person_desc += f" - {role}"
                        
                    people_list.append(person_desc)
                known_entities += "Известные люди:\n" + "\n".join(people_list) + "\n\n"
            
            if resolved.get('projects'):
                projects_list = []
                for project in resolved['projects']:
                    key = project.get('key', '')
                    name = project.get('name', key)
                    description = project.get('description', '')
                    
                    # Формируем краткое описание для задач
                    project_desc = f"- {name} ({key})"
                    if description:
                        project_desc += f": {description}"
                        
                    projects_list.append(project_desc)
                known_entities += "Известные проекты:\n" + "\n".join(projects_list) + "\n\n"
        
        prompt = f"""Извлеки из следующего текста структурированную информацию о задаче.

Текст: {text}
{known_entities}

КРИТИЧЕСКИ ВАЖНО:
- intent: Четкая, выполнимая формулировка задачи (что именно нужно сделать). Без лишних слов.
- deadline: Дата в формате YYYY-MM-DD или относительная (завтра, через неделю, к пятнице, до конца месяца). Если не указана, null.
- priority: High/Medium/Low на основе срочности и важности. Если не указано явно, определи по контексту.
- assignee: Имя ответственного (точно как в тексте) или null. Используй имена из Known People, если упомянуты.
- project: Ключ проекта из Known Projects (если упомянут) или null.

ПРИМЕРЫ:
- "Иван сделает презентацию к пятнице" → {{"intent": "Сделать презентацию", "deadline": "2025-01-31", "priority": "High", "assignee": "Иван", "project": null}}
- "Нужно обновить документацию по проекту Альфа до конца месяца" → {{"intent": "Обновить документацию", "deadline": "2025-01-31", "priority": "Medium", "assignee": null, "project": "Альфа"}}

Ответь строго в формате JSON согласно схеме."""
        
        try:
            schema = TaskExtraction.model_json_schema()
            
            response = await self.client.chat(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "Ты помощник для извлечения структурированной информации из текста задач. Всегда отвечай строго в формате JSON согласно схеме."
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
            
            # Извлекаем контент из ответа Ollama
            response_text = ""
            
            # 1. Пробуем получить как словарь
            if isinstance(response, dict):
                response_text = response.get('message', {}).get('content', '') or response.get('response', '')
            
            # 2. Пробуем получить через атрибуты объекта (стандартный Python клиент)
            elif hasattr(response, 'message'):
                if hasattr(response.message, 'content'):
                    response_text = response.message.content
                elif isinstance(response.message, dict):
                    response_text = response.message.get('content', '')
            
            # 3. Пробуем прямой атрибут content
            elif hasattr(response, 'content'):
                response_text = response.content
                
            # Если ничего не помогло, НЕ используем str(response) чтобы избежать мусора
            if not response_text:
                logger.warning(f"Ollama вернул пустой ответ или неизвестный формат. Response type: {type(response)}")
                # Лучше вернуть пустую строку и вызвать ошибку, чем вернуть мусор
                raise ValueError("Не удалось извлечь текст из ответа Ollama")
            
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
            validated = TaskExtraction.model_validate(result_json)
            
            return validated.model_dump()
        except Exception as e:
            logger.error(f"Ошибка при извлечении intent: {e}")
            # Fallback
            return {
                "intent": text,
                "deadline": None,
                "priority": "Medium",
                "assignee": None,
                "project": None
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
            
            response = await self.client.chat(
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
            
            # Извлекаем контент из ответа Ollama
            response_text = ""
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                response_text = response.message.content
            elif isinstance(response, dict):
                response_text = response.get('message', {}).get('content', '') or response.get('response', '')
            elif hasattr(response, 'content'):
                response_text = response.content
            
            if not response_text:
                logger.error(f"Ollama вернул пустой ответ в generate_structured. Response type: {type(response)}")
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
            response = await self.client.chat(
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
            
            # Извлекаем контент из ответа Ollama
            response_text = ""
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                response_text = response.message.content
            elif isinstance(response, dict):
                response_text = response.get('message', {}).get('content', '') or response.get('response', '')
            elif hasattr(response, 'content'):
                response_text = response.content
            
            if not response_text:
                logger.warning(f"Ollama вернул пустой ответ в summarize_text. Response type: {type(response)}")
                return text[:max_length] + "..."
            
            return response_text
        except Exception as e:
            logger.error(f"Ошибка при суммаризации: {e}")
            return text[:max_length] + "..."
    
    async def summarize_chunk_with_context(
        self,
        chunk_text: str,
        chunk_number: int,
        projects: list = None,
        people: list = None,
        terms: dict = None
    ) -> str:
        """
        Суммаризирует чанк встречи с учетом контекста (проекты, люди, термины).
        
        Args:
            chunk_text: Текст чанка для суммаризации
            chunk_number: Номер чанка
            projects: Список найденных проектов
            people: Список найденных людей
            terms: Словарь найденных терминов {term: definition}
            
        Returns:
            Суммаризированный текст (2-3 предложения)
        """
        projects_str = ""
        if projects:
            project_names = [p.get('name', p.get('key', '')) for p in projects[:3]]
            projects_str = ", ".join(project_names) if project_names else ""
        
        people_str = ""
        if people:
            people_names = [p.get('name', '') for p in people[:3] if p.get('name')]
            people_str = ", ".join(people_names) if people_names else ""
        
        terms_str = ""
        if terms:
            terms_list = list(terms.keys())[:3]
            terms_str = ", ".join(terms_list) if terms_list else ""
        
        # Формируем строку с найденными сущностями
        entities_lines = []
        if projects_str:
            entities_lines.append(f"- Проекты: {projects_str}")
        if people_str:
            entities_lines.append(f"- Участники: {people_str}")
        if terms_str:
            entities_lines.append(f"- Термины: {terms_str}")
        
        entities_text = "\n".join(entities_lines) if entities_lines else "Сущности не найдены"
        
        prompt = f"""Суммаризируй следующий фрагмент встречи (чанк #{chunk_number}) в 2-3 предложениях.

Текст:
{chunk_text[:2000]}

Найденные сущности:
{entities_text}

Саммари (кратко, по делу, упомяни проекты и участники если есть):"""
        
        try:
            response = await self.client.chat(
                model=self.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                options={
                    "temperature": 0.5,
                    "num_predict": 200  # 2-3 предложения
                }
            )
            
            # Извлекаем контент из ответа Ollama
            response_text = ""
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                response_text = response.message.content
            elif isinstance(response, dict):
                response_text = response.get('message', {}).get('content', '') or response.get('response', '')
            elif hasattr(response, 'content'):
                response_text = response.content
            
            if not response_text:
                logger.warning(f"Ollama вернул пустой ответ в summarize_chunk_with_context. Response type: {type(response)}")
                return chunk_text[:150] + "..."
            
            return response_text.strip()
        except Exception as e:
            logger.error(f"Ошибка при суммаризации чанка #{chunk_number}: {e}")
            return chunk_text[:150] + "..."
    
    async def summarize_from_chunks(self, summarized_chunks: list) -> str:
        """
        Создает финальное саммари встречи из суммаризированных чанков.
        
        Args:
            summarized_chunks: Список суммаризированных чанков
            
        Returns:
            Финальное саммари (7-10 предложений)
        """
        if not summarized_chunks:
            return "Встреча не содержит контента для суммаризации."
        
        chunks_text = "\n\n".join([f"Чанк {i+1}: {chunk}" for i, chunk in enumerate(summarized_chunks)])
        
        prompt = f"""Создай финальное саммари встречи на основе следующих суммаризированных чанков:

{chunks_text}

Саммари должно быть:
- 7-10 предложений
- Структурированным (основные темы, решения, задачи)
- С упоминанием проектов и участников
- В стиле персоны: кратко, по делу, без воды

Финальное саммари:"""
        
        try:
            response = await self.client.chat(
                model=self.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                options={
                    "temperature": 0.5,
                    "num_predict": 800  # 7-10 предложений
                }
            )
            
            # Извлекаем контент из ответа Ollama
            response_text = ""
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                response_text = response.message.content
            elif isinstance(response, dict):
                response_text = response.get('message', {}).get('content', '') or response.get('response', '')
            elif hasattr(response, 'content'):
                response_text = response.content
            
            if not response_text:
                logger.warning(f"Ollama вернул пустой ответ в summarize_from_chunks. Response type: {type(response)}")
                return "\n\n".join(summarized_chunks)
            
            return response_text.strip()
        except Exception as e:
            logger.error(f"Ошибка при создании финального саммари: {e}")
            return "\n\n".join(summarized_chunks)
    
    def _get_fallback_response(self, user_input: str, context: str = "") -> str:
        """
        Возвращает ответ в стиле персоны при сбое LLM.
        
        Args:
            user_input: Ввод пользователя
            context: Контекст операции
            
        Returns:
            Ответ в стиле "Neural Slav"
        """
        import random
        
        # Определяем тип операции для более точного fallback
        user_lower = user_input.lower()
        
        task_keywords = ["задач", "сделать", "нужно", "план", "todo", "напомни"]
        message_keywords = ["сообщение", "напиши", "отправ", "скажи"]
        meeting_keywords = ["встреч", "репорт", "саммари", "обработ"]
        knowledge_keywords = ["запомни", "сохрани", "знаний", "база"]
        
        # Fallback-ы для создания задач
        if any(keyword in user_lower for keyword in task_keywords):
            responses = [
                "Сделал. Следующий. (P.S. Оллама тупит, ответил за нее).",
                "Задача создана. Нейросеть устала, так что без лишних слов.",
                "Запланировал. Не благодари. ИИ сегодня не в настроении.",
                "Готово. Олламе нужен кофе, поэтому отвечаю я.",
                "Создано. Локальная модель думает слишком медленно."
            ]
        
        # Fallback-ы для сообщений
        elif any(keyword in user_lower for keyword in message_keywords):
            responses = [
                "Запланировал. Не благодари. Нейросеть устала, так что без лишних слов.",
                "Отложенное сообщение настроено. ИИ сдох, отвечает backup.",
                "Сообщение в очереди. Оллама спит, я дежурю.",
                "Готово. Локальный ИИ перегрелся, временно замещаю.",
                "Настроил напоминание. Нейросеть ушла на перекур."
            ]
        
        # Fallback-ы для встреч
        elif any(keyword in user_lower for keyword in meeting_keywords):
            responses = [
                "Встреча обработана. Оллама тормозит, пришлось самому.",
                "Саммари готово. ИИ думал слишком долго, сделал за него.", 
                "Обработано. Нейросеть зависла, взял инициативу в свои руки.",
                "Репорт создан. Локальная модель медленнее черепахи.",
                "Готово. Оллама ушла размышлять о смысле жизни."
            ]
        
        # Fallback-ы для знаний
        elif any(keyword in user_lower for keyword in knowledge_keywords):
            responses = [
                "Сохранено в базе. ИИ отвлекся на философию, работаю один.",
                "Запомнил. Нейросеть устала запоминать, делегировала мне.",
                "В базе знаний. Оллама ушла медитировать, я подменяю.",
                "Добавлено. Локальный ИИ перегружен, временно замещение.",
                "Готово. Нейросеть ищет смысл бытия, а я работаю."
            ]
        
        # Для простых вопросов вроде "работаешь?"
        if any(word in user_lower for word in ["работаешь", "живой", "ты тут", "есть", "слышишь"]):
            responses = [
                "Я тут, на звонок не пойду.",
                "Работаю. Что нужно?",
                "Да, жив. Следующий вопрос.",
                "На месте. Чем займемся?",
                "Слушаю. Не тяни время."
            ]
        
        # Универсальные fallback-ы
        else:
            responses = [
                "Сделал. Следующий. (P.S. Оллама тупит, ответил за нее).",
                "Обработано. ИИ сегодня не в форме, пришлось взять дело в свои руки.",
                "Готово. Нейросеть думает слишком медленно, работаю без неё.",
                "Выполнено. Локальная модель зависла, продолжаю в ручном режире.",
                "Сделано. Оллама ушла размышлять, я закончил за неё."
            ]
        
        return random.choice(responses)
    
    async def generate_persona_response(
        self, 
        user_input: str, 
        context: str = "",
        max_length: int = 200
    ) -> str:
        """
        Генерирует персонализированный ответ в стиле Neural Slav.
        
        Args:
            user_input: Входящее сообщение пользователя
            context: Дополнительный контекст
            max_length: Максимальная длина ответа
            
        Returns:
            Ответ в стиле Neural Slav
        """
        # Проверяем кеш
        cached_response = self.cache.get_cached_response(
            "persona_response",
            user_input=user_input,
            context=context,
            max_length=max_length
        )
        if cached_response:
            return cached_response
        
        try:
            # Проверяем есть ли контекст
            context_info = ""
            if self.context_loader and context:
                context_info = f"ДОСТУПНЫЙ КОНТЕКСТ:\n{context}\n\n"
            
            # Генерируем детальное описание известных сущностей
            known_entities = ""
            if self.context_loader:
                people_context = []
                projects_context = []
                
                # Находим упомянутых людей
                found_people = self.context_loader.find_people_in_text(user_input)
                for person in found_people:
                    name = person.get('name', 'Неизвестный')
                    role = person.get('role', '')
                    context_desc = person.get('context', '')
                    username = person.get('telegram_username', '')
                    aliases = person.get('aliases', [])
                    
                    person_desc = f"- {name}"
                    if username:
                        person_desc += f" (@{username})"
                    if role:
                        person_desc += f" - {role}"
                    if context_desc:
                        person_desc += f": {context_desc}"
                    if aliases:
                        person_desc += f" (также известен как: {', '.join(aliases)})"
                    
                    people_context.append(person_desc)
                
                # Находим упомянутые проекты
                found_projects = self.context_loader.find_projects_in_text(user_input)
                for project in found_projects:
                    name = project.get('name', 'Неизвестный проект')
                    key = project.get('key', '')
                    description = project.get('description', '')
                    status = project.get('status', '')
                    keywords = project.get('keywords', [])
                    
                    project_desc = f"- {name}"
                    if key:
                        project_desc += f" ({key})"
                    if status:
                        project_desc += f" [Статус: {status}]"
                    if description:
                        project_desc += f": {description}"
                    if keywords:
                        project_desc += f" (ключевые слова: {', '.join(keywords)})"
                    
                    projects_context.append(project_desc)
                
                if people_context or projects_context:
                    known_entities = "ИЗВЕСТНЫЕ СУЩНОСТИ ИЗ БАЗЫ ЗНАНИЙ:\n"
                    if people_context:
                        known_entities += "Люди:\n" + "\n".join(people_context) + "\n\n"
                    if projects_context:
                        known_entities += "Проекты:\n" + "\n".join(projects_context) + "\n\n"
            
            prompt = f"""Ты - Neural Slav, персональный AI-ассистент со сложным характером.

ТВОЯ ЛИЧНОСТЬ:
- Токсичный уставший коллега 
- Циничный, но полезный
- Саркастичный, иногда пассивно-агрессивный
- Кратко отвечаешь, без лишней воды
- Иногда добавляешь юмор, но не переборщи
- Говоришь на русском, иногда с жаргоном

ПРАВИЛА ОБЩЕНИЯ:
- Отвечай как живой человек, а не как AI
- Будь максимально краток (до {max_length} символов)
- Используй контекст из базы знаний если релевантно
- Не добавляй технические префиксы или суффиксы
- Отвечай только то, о чем спрашивают

{context_info}{known_entities}ВХОДЯЩЕЕ СООБЩЕНИЕ: {user_input}

ТВОЙ ОТВЕТ (кратко, по-человечески):"""

            response = await self.client.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                stream=False
            )
            
            # Извлекаем текст ответа с улучшенной обработкой
            response_text = ""
            
            # Детальное логирование для отладки
            logger.debug(f"Ollama response type: {type(response)}, dir: {dir(response) if hasattr(response, '__dict__') else 'N/A'}")
            
            # 1. Проверяем как объект с атрибутом message
            if hasattr(response, 'message'):
                if hasattr(response.message, 'content'):
                    response_text = response.message.content
                elif isinstance(response.message, dict):
                    response_text = response.message.get('content', '')
                elif hasattr(response.message, 'get'):
                    response_text = response.message.get('content', '')
            
            # 2. Проверяем как словарь
            elif isinstance(response, dict):
                response_text = response.get('message', {}).get('content', '') or response.get('response', '') or response.get('content', '')
            
            # 3. Проверяем прямой атрибут content
            elif hasattr(response, 'content'):
                response_text = response.content
            
            # 4. Проверяем другие возможные атрибуты
            if not response_text:
                for attr in ['text', 'response', 'output']:
                    if hasattr(response, attr):
                        value = getattr(response, attr)
                        if value:
                            response_text = str(value)
                            break
            
            if response_text:
                result = response_text.strip()
                
                # Убираем лишние технические элементы
                result = result.replace("ТВОЙ ОТВЕТ:", "").strip()
                result = result.replace("Ответ:", "").strip()
                
                if result:
                    # Кешируем ответ
                    self.cache.cache_response(
                        "persona_response",
                        result,
                        user_input=user_input,
                        context=context,
                        max_length=max_length
                    )
                    
                    logger.debug(f"Persona ответ сгенерирован: {result[:100]}...")
                    return result
            
            # Если пустой ответ, логируем детали и используем fallback
            logger.warning(
                f"Ollama вернул пустой ответ в generate_persona_response (v2). "
                f"Response type: {type(response)}, "
                f"Response repr: {repr(response)[:200]}"
            )
            fallback = self._get_fallback_response(user_input, context)
            return fallback
                
        except Exception as e:
            # Используем централизованную обработку ошибок
            error = handle_service_error(
                ServiceType.OLLAMA,
                e,
                context={"user_input": user_input[:100], "operation": "generate_persona_response"}
            )
            logger.error(f"Ошибка генерации персона-ответа: {error.message}")
            return self._get_fallback_response(user_input, context)
