"""
Сервис для работы с Ollama (локальный AI).
Использует нативную библиотеку ollama для подключения к локальному серверу.
"""
import json
from typing import TypeVar, Type, List, Dict, Any
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

from .config import get_settings
from .context_loader import ContextLoader

T = TypeVar('T', bound=BaseModel)


class OllamaClient:
    """Клиент для работы с Ollama."""
    
    def __init__(self, context_loader: ContextLoader | None = None):
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
        sender_username: str | None = None
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
                if resolved['people']:
                    people_list = []
                    for person in resolved['people']:
                        name = person.get('name', '')
                        username = person.get('telegram_username', '')
                        role = person.get('role', '')
                        aliases = person.get('aliases', [])
                        aliases_str = f" (также известен как: {', '.join(aliases)})" if aliases else ""
                        # Формат: Name -> @tag для четкого маппинга
                        tag_str = f"@{username}" if username else "(нет @tag)"
                        people_list.append(f"- {name} -> {tag_str} ({role}){aliases_str}")
                    known_entities += "Known People (Name -> @tag):\n" + "\n".join(people_list) + "\n\n"
                
                if resolved['projects']:
                    projects_list = []
                    for project in resolved['projects']:
                        key = project.get('key', '')
                        description = project.get('description', '')
                        keywords = project.get('keywords', [])
                        keywords_str = f" (ключевые слова: {', '.join(keywords)})" if keywords else ""
                        projects_list.append(f"- {key}: {description}{keywords_str}")
                    known_entities += "Known Projects:\n" + "\n".join(projects_list) + "\n\n"
                
                # Релевантные проекты из контента (для обратной совместимости)
                projects_context = self.context_loader.enrich_message_with_projects(content)
                if projects_context:
                    context_info += f"Relevant Projects:\n{projects_context}\n"
                
                # Поиск терминов глоссария в контенте (keyword matching)
                glossary_terms = self.context_loader.find_glossary_terms(content)
                if glossary_terms:
                    glossary_list = []
                    for term, definition in glossary_terms.items():
                        # Формат: Term -> Definition для четкого маппинга
                        glossary_list.append(f"- {term} -> {definition}")
                    known_entities += "Glossary (Term -> Definition):\n" + "\n".join(glossary_list) + "\n\n"
            
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

INPUT CONTEXT:
Ты получаешь список `Known People` (Name -> @tag) и `Glossary` (Term -> Definition).

ПРАВИЛА ДЛЯ ТЕГИРОВАНИЯ ЛЮДЕЙ:
- Если упоминаешь человека из списка Known People, ОБЯЗАТЕЛЬНО используй его @tag.
- Формат: "Иван (@ivan_dev) должен..." или "Поручили @ivan_dev задачу..."
- Если человека нет в списке Known People — пиши имя текстом без @tag.

ПРАВИЛА ДЛЯ ГЛОССАРИЯ:
- Если встречаешь термин из Глоссария, при первом упоминании дай короткое пояснение в скобках.
- Пример: "Обсудили РЛС (Руководитель лёгкой сети) и его функции..."
- При последующих упоминаниях можно использовать термин без пояснения.

Пример Инсайта:
"💡 <i>Инсайт:</i> Команда обсуждает интерфейс уже 3-й митинг подряд, но ТЗ до сих пор нет. Похоже на имитацию бурной деятельности со стороны Дизайна."

Всегда отвечай только валидным JSON согласно схеме."""
            
            if known_entities:
                system_prompt += f"\n\nKNOWN ENTITIES:\n{known_entities}"
                system_prompt += "\n\nВАЖНО: "
                system_prompt += "1. Если в тексте встречаются имена или упоминания проектов, используй предоставленный список Known Entities, чтобы понять, о ком/чем речь, даже если имя написано не полностью или используется алиас (например, 'Ваня' вместо 'Иван Тихомиров', или 'Тихомиров' вместо полного имени). "
                system_prompt += "2. При упоминании человека из Known People ОБЯЗАТЕЛЬНО используй его @tag (формат: Name -> @tag). "
                system_prompt += "3. При первом упоминании термина из Glossary дай краткое пояснение в скобках (формат: Term -> Definition)."
            
            if context_info:
                system_prompt += f"\n\nCONTEXT INFO:\n{context_info}"
            
            prompt = f"""Проанализируй следующую встречу и извлеки структурированную информацию.
{context_text}

Транскрипция встречи:
{content[:4000]}

ВАЖНО: 
- Ответь строго в формате JSON согласно схеме.
- summary_md должен быть в HTML формате с тегами <b>, <i>, <blockquote>, <a>.
- Структура summary_md:
  1. 🎯 <b>Суть:</b> Одно предложение. О чем говорили.
  2. 💡 <b>Инсайт:</b> Твой аналитический комментарий (что между строк, риски, кто тормозит). Выдели <blockquote> или 💡.
  3. 📋 <b>Решения и Задачи:</b> Список Action Items с именами ответственных.
  4. ⚠️ <b>Риски:</b> Если есть.
- Саммари должно быть кратким (до 500 слов), без вступительных слов, сразу к сути.
- Список задач ограничь 15 наиболее важными.
- Задачи должны быть в повелительном наклонении с указанием имени и @tag в формате: <b>Имя (@tag):</b> Задача.
- При упоминании людей из Known People ОБЯЗАТЕЛЬНО используй их @tag.
- При первом упоминании термина из Glossary дай краткое пояснение в скобках (например: "РЛС (Руководитель лёгкой сети)")."""
            
            # Генерируем JSON схему из Pydantic модели
            schema = response_schema.model_json_schema()
            
            logger.info(f"Вызов Ollama {self.model_name} для анализа встречи")
            
            # Используем нативную библиотеку ollama
            # Для новых версий Ollama используем chat() как основной метод
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
                # Ollama chat API возвращает объект с полем 'message' -> 'content'
                logger.debug(f"Сырой ответ от Ollama (тип: {type(response)}): {response}")
                if isinstance(response, dict):
                    response_text = response.get('message', {}).get('content', '') or response.get('response', '')
                elif hasattr(response, 'message'):
                    response_text = response.message.content if hasattr(response.message, 'content') else str(response.message)
                else:
                    response_text = str(response)
                
                if not response_text:
                    logger.error(f"Пустой ответ от Ollama. Полный объект: {response}")
                    raise ValueError("Ollama вернул пустой ответ")
            except (AttributeError, TypeError, KeyError) as e:
                # Если метод chat не существует или не работает, пробуем generate (fallback для старых версий)
                logger.debug(f"Метод chat не сработал: {e}, пробуем generate")
                try:
                    full_prompt = f"""{system_prompt}

{prompt}

JSON схема:
{json.dumps(schema, indent=2, ensure_ascii=False)}

Ответь ТОЛЬКО валидным JSON объектом без дополнительных комментариев."""
                    response = self.client.generate(
                        model=self.model_name,
                        prompt=full_prompt,
                        options={
                            "temperature": self.temperature,
                            "num_predict": self.max_tokens
                        }
                    )
                    # Ollama generate API возвращает объект с полем 'response'
                    response_text = response.get('response', '') if isinstance(response, dict) else str(response)
                except Exception as e2:
                    logger.error(f"Оба метода ollama не сработали: {e2}")
                    raise ValueError(f"Не удалось вызвать Ollama: {e2}")
            
            # Проверяем, что ответ не пустой
            if not response_text:
                logger.error("Ollama вернул пустой ответ")
                raise ValueError("Empty response from Ollama")
            
            # Парсим и валидируем ответ
            try:
                # Очищаем ответ от возможных markdown блоков кода
                text = response_text.strip()
                if text.startswith("```json"):
                    text = text[7:]
                elif text.startswith("```"):
                    text = text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
                
                # Пытаемся исправить распространенные проблемы с JSON
                import re
                text = re.sub(r',\s*}', '}', text)
                text = re.sub(r',\s*]', ']', text)
                
                result_json = json.loads(text)
                validated = response_schema.model_validate(result_json)
            except ValidationError as e:
                logger.error(f"Ошибка валидации ответа Ollama: {e}")
                logger.debug(f"Сырой ответ: {response_text[:500]}")
                raise
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON от Ollama: {e}")
                logger.debug(f"Сырой ответ: {response_text[:500]}")
                raise
            
            # Получаем количество задач безопасным способом
            action_items_count = 0
            if hasattr(validated, 'action_items'):
                action_items_count = len(validated.action_items)  # type: ignore
            
            logger.info(
                f"Успешно проанализирована встреча через {self.model_name}, "
                f"извлечено {action_items_count} задач"
            )
            return validated
            
        except Exception as e:
            logger.error(f"Ошибка при анализе встречи через {self.model_name}: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ValueError, ValidationError, json.JSONDecodeError)),
        reraise=True
    )
    async def classify_message(
        self,
        text: str,
        author_name: str,
        author_role: str,
        author_username: str | None = None
    ) -> Dict[str, Any]:
        """
        Классифицирует входящее сообщение.
        
        Args:
            text: Текст сообщения
            author_name: Имя автора
            author_role: Роль автора
            author_username: Username автора (опционально, для контекста)
            
        Returns:
            Словарь с полями: type, summary, datetime, action_needed
        """
        try:
            # Добавляем контекст отправителя и проектов
            context_info = ""
            known_entities = ""
            
            if self.context_loader:
                # Контекст отправителя
                if author_username:
                    person_context = self.context_loader.get_person_context(author_username)
                    if person_context:
                        context_info += f"Sender: {person_context}\n"
                
                # Умный поиск людей и проектов в тексте
                resolved = self.context_loader.resolve_entity(text)
                
                # Формируем список известных сущностей для LLM
                if resolved['people']:
                    people_list = []
                    for person in resolved['people']:
                        name = person.get('name', '')
                        username = person.get('telegram_username', '')
                        role = person.get('role', '')
                        aliases = person.get('aliases', [])
                        aliases_str = f" (также известен как: {', '.join(aliases)})" if aliases else ""
                        # Формат: Name -> @tag для четкого маппинга
                        tag_str = f"@{username}" if username else "(нет @tag)"
                        people_list.append(f"- {name} -> {tag_str} ({role}){aliases_str}")
                    known_entities += "Known People (Name -> @tag):\n" + "\n".join(people_list) + "\n\n"
                
                if resolved['projects']:
                    projects_list = []
                    for project in resolved['projects']:
                        key = project.get('key', '')
                        description = project.get('description', '')
                        keywords = project.get('keywords', [])
                        keywords_str = f" (ключевые слова: {', '.join(keywords)})" if keywords else ""
                        projects_list.append(f"- {key}: {description}{keywords_str}")
                    known_entities += "Known Projects:\n" + "\n".join(projects_list) + "\n\n"
                
                # Релевантные проекты из текста (для обратной совместимости)
                projects_context = self.context_loader.enrich_message_with_projects(text)
                if projects_context:
                    context_info += f"Relevant Projects:\n{projects_context}\n"
            
            system_prompt = "Ты помощник для классификации сообщений. Всегда отвечай только валидным JSON."
            
            if known_entities:
                system_prompt += f"\n\nKNOWN ENTITIES:\n{known_entities}"
                system_prompt += "ВАЖНО: Если в тексте встречаются имена или упоминания проектов, используй предоставленный список Known Entities, чтобы понять, о ком/чем речь, даже если имя написано не полностью или используется алиас (например, 'Ваня' вместо 'Иван Тихомиров', или 'Тихомиров' вместо полного имени)."
            
            if context_info:
                system_prompt += f"\n\nCONTEXT INFO:\n{context_info}"
            
            prompt = f"""Анализируй сообщение от {author_name} ({author_role}): '{text}'

Классифицируй и верни JSON:
{{
  "type": "task" | "reminder" | "knowledge",
  "summary": "...",
  "datetime": "YYYY-MM-DD HH:MM" (только если это напоминание, иначе null),
  "action_needed": true/false
}}"""
            
            logger.info(f"Классификация сообщения через Ollama {self.model_name}")
            
            # Используем chat() как основной метод
            try:
                response = self.client.chat(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "system",
                            "content": system_prompt
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    options={
                        "temperature": self.temperature,
                        "num_predict": 512
                    }
                )
                # Ollama chat API возвращает объект с полем 'message' -> 'content'
                if isinstance(response, dict):
                    response_text = response.get('message', {}).get('content', '') or response.get('response', '')
                else:
                    response_text = str(response)
            except (AttributeError, TypeError, KeyError) as e:
                # Если метод chat не существует или не работает, пробуем generate (fallback для старых версий)
                logger.debug(f"Метод chat не сработал: {e}, пробуем generate")
                try:
                    full_prompt = f"""{system_prompt}

{prompt}

Ответь ТОЛЬКО валидным JSON объектом без дополнительных комментариев."""
                    response = self.client.generate(
                        model=self.model_name,
                        prompt=full_prompt,
                        options={
                            "temperature": self.temperature,
                            "num_predict": 512
                        }
                    )
                    response_text = response.get('response', '') if isinstance(response, dict) else str(response)
                except Exception as e2:
                    logger.error(f"Оба метода ollama не сработали: {e2}")
                    raise ValueError(f"Не удалось вызвать Ollama: {e2}")
            
            if not response_text:
                raise ValueError("Empty response from Ollama")
            
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
            
            result = json.loads(text)
            
            logger.info(f"Сообщение классифицировано как: {result.get('type')}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при классификации сообщения: {e}")
            raise
    
    def enrich_mentions(self, text: str) -> str:
        """
        Обогащает текст, заменяя имена людей на Telegram ссылки.
        Ищет имена/алиасы из people_map и заменяет их на HTML ссылки.
        
        Args:
            text: Текст для обогащения
            
        Returns:
            Текст с замененными именами на Telegram ссылки
        """
        if not self.context_loader:
            return text
        
        import re
        
        # Создаем карту всех вариантов имен -> username для замены
        # Формат: {name_lower: (original_name, username)}
        name_map = {}
        
        for username_lower, person_data in self.context_loader.people.items():
            username = person_data.get('telegram_username', '')
            name = person_data.get('name', '')
            aliases = person_data.get('aliases', [])
            
            # Добавляем основное имя
            if name:
                name_lower = name.lower()
                if name_lower not in name_map:
                    name_map[name_lower] = (name, username)
            
            # Добавляем алиасы
            for alias in aliases:
                if alias:
                    alias_lower = alias.lower().strip()
                    if alias_lower not in name_map:
                        name_map[alias_lower] = (alias, username)
        
        # Сортируем по длине (сначала длинные имена, чтобы не заменять части слов)
        sorted_names = sorted(name_map.items(), key=lambda x: len(x[0]), reverse=True)
        
        result = text
        # Отслеживаем уже замененные части, чтобы не заменять внутри ссылок
        replaced_positions = []
        
        for name_lower, (original_name, username) in sorted_names:
            if not original_name or len(original_name) < 2:
                continue
            
            # Ищем все вхождения имени в тексте (case-insensitive)
            pattern = re.compile(re.escape(original_name), re.IGNORECASE)
            
            def replace_match(match):
                start, end = match.span()
                
                # Проверяем, не находимся ли мы внутри уже созданной ссылки
                for (replaced_start, replaced_end) in replaced_positions:
                    if start >= replaced_start and end <= replaced_end:
                        return match.group(0)  # Не заменяем
                
                # Проверяем, не находимся ли мы внутри существующей HTML ссылки
                # Ищем открывающий тег <a перед этой позицией
                text_before = result[:start]
                last_a_open = text_before.rfind('<a ')
                if last_a_open != -1:
                    # Проверяем, есть ли закрывающий тег </a> после открывающего
                    a_close_after_open = text_before.find('</a>', last_a_open)
                    if a_close_after_open == -1:
                        # Мы внутри открытой ссылки, не заменяем
                        return match.group(0)
                
                # Заменяем на ссылку
                if username:
                    # Используем @username формат для упоминаний в Telegram
                    username_clean = username.lstrip('@')
                    replacement = f'<a href="https://t.me/{username_clean}">{original_name}</a>'
                else:
                    # Если нет username, просто оставляем имя
                    replacement = original_name
                
                replaced_positions.append((start, start + len(replacement)))
                return replacement
            
            result = pattern.sub(replace_match, result)
        
        return result