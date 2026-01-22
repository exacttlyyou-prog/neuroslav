"""
Сервис для загрузки и работы с контекстом людей, проектов и глоссария из Notion баз данных.
Кэширует данные в памяти для быстрого доступа.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger
import httpx

from core.config import get_settings
from notion_client import AsyncClient


class ContextLoader:
    """Загрузчик контекста людей, проектов и глоссария из Notion баз данных."""
    
    def __init__(self, data_dir: str = "data"):
        """
        Инициализация загрузчика контекста.
        
        Args:
            data_dir: Директория с JSON файлами (fallback, если Notion не настроен)
        """
        settings = get_settings()
        self.data_dir = Path(data_dir)
        self.people: Dict[str, Dict[str, str]] = {}
        self.projects: List[Dict[str, Any]] = []
        self.glossary: Dict[str, str] = {}  # term_lower -> definition
        
        # Обратный индекс для поиска по всем вариантам имен (алиасам)
        self.people_lookup_map: Dict[str, Dict[str, str]] = {}  # alias_lower -> person_data
        self.projects_lookup_map: Dict[str, Dict[str, Any]] = {}  # keyword_lower -> project_data
        
        # Инициализация Notion клиента
        if settings.notion_token:
            self.notion_client = AsyncClient(auth=settings.notion_token)
            self.notion_people_db_id = settings.notion_people_db_id
            self.notion_projects_db_id = settings.notion_projects_db_id
            self.notion_glossary_db_id = settings.notion_glossary_db_id
        else:
            self.notion_client = None
            self.notion_people_db_id = None
            self.notion_projects_db_id = None
            self.notion_glossary_db_id = None
            logger.warning("NOTION_TOKEN не установлен, используем fallback на JSON файлы")
        
        # Загружаем только JSON fallback при инициализации (синхронно)
        # Notion загрузится позже через sync_context_from_notion() (async)
        self._load_from_json()
        # Строим обратный индекс после загрузки JSON
        self._build_lookup_maps()
    
    def _load_from_json(self):
        """Загрузить контекст из JSON файлов (fallback)."""
        self._load_people_json()
        self._load_projects_json()
    
    def _load_people_json(self):
        """Загрузить people.json (fallback)."""
        people_file = self.data_dir / "people.json"
        try:
            if people_file.exists():
                with open(people_file, 'r', encoding='utf-8') as f:
                    people_data = json.load(f)
                    # Конвертируем в нужный формат
                    self.people = {}
                    for username, data in people_data.items():
                        self.people[username.lower()] = {
                            'role': data.get('role', 'Unknown'),
                            'context': data.get('context', ''),
                            'name': data.get('name', username)
                        }
                logger.info(f"Загружено {len(self.people)} записей о людях из {people_file}")
            else:
                logger.warning(f"Файл {people_file} не найден")
                self.people = {}
        except Exception as e:
            logger.error(f"Ошибка при загрузке people.json: {e}")
            self.people = {}
    
    def _load_projects_json(self):
        """Загрузить projects.json (fallback)."""
        projects_file = self.data_dir / "projects.json"
        try:
            if projects_file.exists():
                with open(projects_file, 'r', encoding='utf-8') as f:
                    projects_data = json.load(f)
                    # Конвертируем в нужный формат
                    self.projects = []
                    for key, data in projects_data.items():
                        self.projects.append({
                            'keywords': data.get('keywords', []),
                            'description': data.get('description', ''),
                            'status': data.get('status', 'unknown'),
                            'key': key
                        })
                logger.info(f"Загружено {len(self.projects)} проектов из {projects_file}")
            else:
                logger.warning(f"Файл {projects_file} не найден")
                self.projects = []
        except Exception as e:
            logger.error(f"Ошибка при загрузке projects.json: {e}")
            self.projects = []
    
    async def sync_context_from_notion(self):
        """
        Синхронизировать контекст из Notion баз данных.
        Загружает данные и кэширует в памяти.
        """
        if not self.notion_client:
            logger.error("Notion клиент не инициализирован")
            return
        
        logger.info("Синхронизация контекста из Notion...")
        
        # Загружаем People
        if self.notion_people_db_id:
            await self._load_people_from_notion()
        else:
            logger.warning("NOTION_PEOPLE_DB_ID не установлен, пропускаем загрузку людей")
        
        # Загружаем Projects
        if self.notion_projects_db_id:
            await self._load_projects_from_notion()
        else:
            logger.warning("NOTION_PROJECTS_DB_ID не установлен, пропускаем загрузку проектов")
        
        # Загружаем Glossary
        if self.notion_glossary_db_id:
            await self._load_glossary_from_notion()
        else:
            logger.warning("NOTION_GLOSSARY_DB_ID не установлен, пропускаем загрузку глоссария")
        
        logger.info(f"Синхронизация завершена: {len(self.people)} людей, {len(self.projects)} проектов, {len(self.glossary)} терминов в глоссарии")
        
        # Перестраиваем индексы после синхронизации
        self._build_lookup_maps()
    
    async def _load_people_from_notion(self):
        """Загрузить людей из Notion базы данных."""
        try:
            # Используем прямой HTTP запрос к Notion API для запроса базы данных
            # так как notion-client не имеет метода query для databases
            settings = get_settings()
            headers = {
                "Authorization": f"Bearer {settings.notion_token}",
                "Notion-Version": "2025-09-03",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.notion.com/v1/databases/{self.notion_people_db_id}/query",
                    headers=headers,
                    json={}  # Пустой запрос для получения всех записей
                )
                response.raise_for_status()
                data = response.json()
            
            self.people = {}
            
            for page in data.get('results', []):
                properties = page.get('properties', {})
                
                # Ищем колонку "Telegram" (может быть разных типов)
                telegram_username = None
                telegram_prop = properties.get('Telegram') or properties.get('telegram') or properties.get('Telegram Username')
                
                if telegram_prop:
                    prop_type = telegram_prop.get('type')
                    if prop_type == 'rich_text':
                        rich_text = telegram_prop.get('rich_text', [])
                        if rich_text:
                            telegram_username = rich_text[0].get('plain_text', '').strip()
                            # Убираем @ если есть
                            if telegram_username.startswith('@'):
                                telegram_username = telegram_username[1:]
                    elif prop_type == 'title':
                        title = telegram_prop.get('title', [])
                        if title:
                            telegram_username = title[0].get('plain_text', '').strip()
                            if telegram_username.startswith('@'):
                                telegram_username = telegram_username[1:]
                
                if not telegram_username:
                    continue
                
                # Получаем Role
                role = 'Unknown'
                role_prop = properties.get('Role') or properties.get('role')
                if role_prop:
                    prop_type = role_prop.get('type')
                    if prop_type == 'select' and role_prop.get('select'):
                        role = role_prop['select'].get('name', 'Unknown')
                    elif prop_type == 'rich_text':
                        rich_text = role_prop.get('rich_text', [])
                        if rich_text:
                            role = rich_text[0].get('plain_text', '').strip()
                
                # Получаем Context
                context = ''
                context_prop = properties.get('Context') or properties.get('context')
                if context_prop:
                    prop_type = context_prop.get('type')
                    if prop_type == 'rich_text':
                        rich_text = context_prop.get('rich_text', [])
                        if rich_text:
                            context = ' '.join([rt.get('plain_text', '') for rt in rich_text])
                    elif prop_type == 'title':
                        title = context_prop.get('title', [])
                        if title:
                            context = title[0].get('plain_text', '').strip()
                
                # Получаем Name (из заголовка страницы или колонки Name)
                name = telegram_username
                name_prop = properties.get('Name') or properties.get('name')
                if name_prop:
                    prop_type = name_prop.get('type')
                    if prop_type == 'title':
                        title = name_prop.get('title', [])
                        if title:
                            name = title[0].get('plain_text', '').strip()
                
                # Получаем Aliases (альтернативные имена)
                aliases = []
                aliases_prop = properties.get('Aliases') or properties.get('aliases')
                if aliases_prop:
                    prop_type = aliases_prop.get('type')
                    if prop_type == 'multi_select':
                        multi_select = aliases_prop.get('multi_select', [])
                        aliases = [item.get('name', '').strip() for item in multi_select if item.get('name')]
                    elif prop_type == 'rich_text':
                        rich_text = aliases_prop.get('rich_text', [])
                        if rich_text:
                            # Разбиваем по запятым или переносам строк
                            aliases_text = ' '.join([rt.get('plain_text', '') for rt in rich_text])
                            aliases = [a.strip() for a in aliases_text.replace(',', ' ').split() if a.strip()]
                
                # Сохраняем в словарь
                username_lower = telegram_username.lower()
                person_data = {
                    'role': role,
                    'context': context,
                    'name': name,
                    'telegram_username': telegram_username,
                    'aliases': aliases
                }
                self.people[username_lower] = person_data
            
            logger.info(f"Загружено {len(self.people)} людей из Notion")
            
            # Строим обратный индекс после загрузки
            self._build_people_lookup_map()
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке людей из Notion: {e}")
            raise
    
    async def _load_projects_from_notion(self):
        """Загрузить проекты из Notion базы данных."""
        try:
            # Используем прямой HTTP запрос к Notion API для запроса базы данных
            # так как notion-client не имеет метода query для databases
            settings = get_settings()
            headers = {
                "Authorization": f"Bearer {settings.notion_token}",
                "Notion-Version": "2025-09-03",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.notion.com/v1/databases/{self.notion_projects_db_id}/query",
                    headers=headers,
                    json={}  # Пустой запрос для получения всех записей
                )
                response.raise_for_status()
                data = response.json()
            
            self.projects = []
            
            for page in data.get('results', []):
                properties = page.get('properties', {})
                
                # Получаем Description
                description = ''
                desc_prop = properties.get('Description') or properties.get('description')
                if desc_prop:
                    prop_type = desc_prop.get('type')
                    if prop_type == 'rich_text':
                        rich_text = desc_prop.get('rich_text', [])
                        if rich_text:
                            description = ' '.join([rt.get('plain_text', '') for rt in rich_text])
                    elif prop_type == 'title':
                        title = desc_prop.get('title', [])
                        if title:
                            description = title[0].get('plain_text', '').strip()
                
                # Получаем Status
                status = 'unknown'
                status_prop = properties.get('Status') or properties.get('status')
                if status_prop:
                    prop_type = status_prop.get('type')
                    if prop_type == 'select' and status_prop.get('select'):
                        status = status_prop['select'].get('name', 'unknown')
                    elif prop_type == 'rich_text':
                        rich_text = status_prop.get('rich_text', [])
                        if rich_text:
                            status = rich_text[0].get('plain_text', '').strip()
                
                # Получаем Keywords (может быть multi_select или rich_text)
                keywords = []
                keywords_prop = properties.get('Keywords') or properties.get('keywords') or properties.get('Tags')
                if keywords_prop:
                    prop_type = keywords_prop.get('type')
                    if prop_type == 'multi_select':
                        multi_select = keywords_prop.get('multi_select', [])
                        keywords = [item.get('name', '') for item in multi_select if item.get('name')]
                    elif prop_type == 'rich_text':
                        rich_text = keywords_prop.get('rich_text', [])
                        if rich_text:
                            # Разбиваем по запятым или пробелам
                            keywords_text = ' '.join([rt.get('plain_text', '') for rt in rich_text])
                            keywords = [k.strip() for k in keywords_text.replace(',', ' ').split() if k.strip()]
                
                # Получаем Key (из заголовка страницы или колонки Name)
                key = ''
                key_prop = properties.get('Name') or properties.get('name') or properties.get('Title')
                if key_prop:
                    prop_type = key_prop.get('type')
                    if prop_type == 'title':
                        title = key_prop.get('title', [])
                        if title:
                            key = title[0].get('plain_text', '').strip()
                
                # Сохраняем в список
                self.projects.append({
                    'keywords': keywords,
                    'description': description,
                    'status': status,
                    'key': key
                })
            
            logger.info(f"Загружено {len(self.projects)} проектов из Notion")
            
            # Строим обратный индекс после загрузки
            self._build_projects_lookup_map()
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке проектов из Notion: {e}")
            raise
    
    async def _load_glossary_from_notion(self):
        """Загрузить глоссарий из Notion базы данных."""
        try:
            # Используем прямой HTTP запрос к Notion API для запроса базы данных
            settings = get_settings()
            headers = {
                "Authorization": f"Bearer {settings.notion_token}",
                "Notion-Version": "2025-09-03",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.notion.com/v1/databases/{self.notion_glossary_db_id}/query",
                    headers=headers,
                    json={}  # Пустой запрос для получения всех записей
                )
                response.raise_for_status()
                data = response.json()
            
            self.glossary = {}
            
            for page in data.get('results', []):
                properties = page.get('properties', {})
                
                # Получаем Term (термин) - обычно это заголовок страницы или колонка Name/Title
                term = ''
                term_prop = properties.get('Term') or properties.get('term') or properties.get('Name') or properties.get('name') or properties.get('Title')
                if term_prop:
                    prop_type = term_prop.get('type')
                    if prop_type == 'title':
                        title = term_prop.get('title', [])
                        if title:
                            term = title[0].get('plain_text', '').strip()
                    elif prop_type == 'rich_text':
                        rich_text = term_prop.get('rich_text', [])
                        if rich_text:
                            term = ' '.join([rt.get('plain_text', '') for rt in rich_text]).strip()
                
                if not term:
                    continue
                
                # Получаем Definition (определение)
                definition = ''
                definition_prop = properties.get('Definition') or properties.get('definition') or properties.get('Description') or properties.get('description')
                if definition_prop:
                    prop_type = definition_prop.get('type')
                    if prop_type == 'rich_text':
                        rich_text = definition_prop.get('rich_text', [])
                        if rich_text:
                            definition = ' '.join([rt.get('plain_text', '') for rt in rich_text])
                    elif prop_type == 'title':
                        title = definition_prop.get('title', [])
                        if title:
                            definition = title[0].get('plain_text', '').strip()
                
                if not definition:
                    continue
                
                # Сохраняем основной термин (в нижнем регистре для поиска)
                term_lower = term.lower()
                self.glossary[term_lower] = definition
                
                # Получаем Synonyms (синонимы) и маппим их на то же определение
                synonyms_prop = properties.get('Synonyms') or properties.get('synonyms') or properties.get('Aliases') or properties.get('aliases')
                if synonyms_prop:
                    prop_type = synonyms_prop.get('type')
                    synonyms = []
                    
                    if prop_type == 'multi_select':
                        multi_select = synonyms_prop.get('multi_select', [])
                        synonyms = [item.get('name', '') for item in multi_select if item.get('name')]
                    elif prop_type == 'rich_text':
                        rich_text = synonyms_prop.get('rich_text', [])
                        if rich_text:
                            # Разбиваем по запятым или пробелам
                            synonyms_text = ' '.join([rt.get('plain_text', '') for rt in rich_text])
                            synonyms = [s.strip() for s in synonyms_text.replace(',', ' ').split() if s.strip()]
                    
                    # Маппим все синонимы на то же определение
                    for synonym in synonyms:
                        if synonym:
                            synonym_lower = synonym.lower()
                            self.glossary[synonym_lower] = definition
            
            logger.info(f"Загружено {len(self.glossary)} терминов в глоссарий из Notion")
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке глоссария из Notion: {e}")
            raise
    
    def _build_lookup_maps(self):
        """Построить обратные индексы для поиска по алиасам."""
        self._build_people_lookup_map()
        self._build_projects_lookup_map()
    
    def _build_people_lookup_map(self):
        """Построить обратный индекс для людей по всем вариантам имен."""
        self.people_lookup_map = {}
        
        for username_lower, person_data in self.people.items():
            # Добавляем telegram username
            self.people_lookup_map[username_lower] = person_data
            
            # Добавляем имя
            name = person_data.get('name', '')
            if name:
                name_lower = name.lower()
                self.people_lookup_map[name_lower] = person_data
                
                # Разбиваем имя на части (для поиска по фамилии)
                name_parts = name_lower.split()
                for part in name_parts:
                    if len(part) > 2:  # Игнорируем очень короткие части
                        self.people_lookup_map[part] = person_data
            
            # Добавляем алиасы
            aliases = person_data.get('aliases', [])
            for alias in aliases:
                if alias:
                    alias_lower = alias.lower().strip()
                    self.people_lookup_map[alias_lower] = person_data
                    
                    # Разбиваем алиас на части
                    alias_parts = alias_lower.split()
                    for part in alias_parts:
                        if len(part) > 2:
                            self.people_lookup_map[part] = person_data
        
        logger.info(f"Построен обратный индекс для {len(self.people_lookup_map)} вариантов имен людей")
    
    def _build_projects_lookup_map(self):
        """Построить обратный индекс для проектов по ключевым словам."""
        self.projects_lookup_map = {}
        
        for project in self.projects:
            # Добавляем название проекта
            key = project.get('key', '')
            if key:
                key_lower = key.lower()
                self.projects_lookup_map[key_lower] = project
                
                # Разбиваем название на части
                key_parts = key_lower.split()
                for part in key_parts:
                    if len(part) > 2:
                        self.projects_lookup_map[part] = project
            
            # Добавляем ключевые слова
            keywords = project.get('keywords', [])
            for keyword in keywords:
                if keyword:
                    keyword_lower = keyword.lower().strip()
                    self.projects_lookup_map[keyword_lower] = project
                    
                    # Разбиваем ключевое слово на части
                    keyword_parts = keyword_lower.split()
                    for part in keyword_parts:
                        if len(part) > 2:
                            self.projects_lookup_map[part] = project
        
        logger.info(f"Построен обратный индекс для {len(self.projects_lookup_map)} вариантов названий проектов")
    
    def reload(self):
        """Перезагрузить контекст из Notion или JSON файлов."""
        logger.info("Перезагрузка контекста...")
        if self.notion_client and self.notion_people_db_id and self.notion_projects_db_id:
            import asyncio
            try:
                asyncio.run(self.sync_context_from_notion())
            except Exception as e:
                logger.error(f"Ошибка при перезагрузке из Notion: {e}, используем fallback")
                self._load_from_json()
        else:
            self._load_from_json()
        
        # Перестраиваем индексы после перезагрузки
        self._build_lookup_maps()
    
    def get_person_context(self, username: Optional[str]) -> str:
        """
        Получить контекст человека по username.
        
        Args:
            username: Telegram username (без @)
            
        Returns:
            Строка с контекстом человека или пустая строка
        """
        if not username:
            return ""
        
        username_lower = username.lower()
        
        # Прямой поиск по username
        if username_lower in self.people:
            person = self.people[username_lower]
            role = person.get("role", "Unknown")
            context = person.get("context", "")
            return f"Role: {role}. {context}".strip()
        
        return ""
    
    def resolve_entity(self, text: str) -> Dict[str, Any]:
        """
        Умный поиск людей и проектов в тексте по всем вариантам имен (алиасам).
        
        Args:
            text: Текст для анализа
            
        Returns:
            Словарь с найденными людьми и проектами:
            {
                'people': [{'name': '...', 'telegram_username': '...', 'role': '...', 'context': '...'}],
                'projects': [{'key': '...', 'description': '...', 'status': '...'}]
            }
        """
        text_lower = text.lower()
        found_people = []
        found_projects = []
        
        # Ищем людей по всем вариантам имен
        seen_people = set()
        for alias, person_data in self.people_lookup_map.items():
            # Проверяем, что алиас достаточно длинный и встречается в тексте
            if len(alias) > 2 and alias in text_lower:
                # Избегаем дубликатов по telegram_username
                telegram_username = person_data.get('telegram_username', '')
                if telegram_username and telegram_username.lower() not in seen_people:
                    seen_people.add(telegram_username.lower())
                    found_people.append({
                        'name': person_data.get('name', ''),
                        'telegram_username': telegram_username,
                        'role': person_data.get('role', 'Unknown'),
                        'context': person_data.get('context', ''),
                        'aliases': person_data.get('aliases', [])
                    })
        
        # Ищем проекты по всем вариантам названий и ключевых слов
        seen_projects = set()
        for keyword, project_data in self.projects_lookup_map.items():
            # Проверяем, что ключевое слово достаточно длинное и встречается в тексте
            if len(keyword) > 2 and keyword in text_lower:
                # Избегаем дубликатов по ключу проекта
                project_key = project_data.get('key', '')
                if project_key and project_key.lower() not in seen_projects:
                    seen_projects.add(project_key.lower())
                    found_projects.append({
                        'key': project_key,
                        'description': project_data.get('description', ''),
                        'status': project_data.get('status', 'unknown'),
                        'keywords': project_data.get('keywords', [])
                    })
        
        return {
            'people': found_people,
            'projects': found_projects
        }
    
    def find_glossary_terms(self, text: str) -> Dict[str, str]:
        """
        Находит термины глоссария в тексте через keyword matching.
        
        Args:
            text: Текст для поиска терминов
            
        Returns:
            Словарь {term: definition} найденных терминов
        """
        if not self.glossary:
            return {}
        
        text_lower = text.lower()
        found_terms = {}
        
        # Ищем все термины из глоссария в тексте
        for term_lower, definition in self.glossary.items():
            # Проверяем, что термин достаточно длинный и встречается в тексте
            if len(term_lower) > 2 and term_lower in text_lower:
                # Используем оригинальный термин (первый ключ, который маппится на это определение)
                # Для простоты используем term_lower, но можно улучшить
                found_terms[term_lower] = definition
        
        return found_terms
    
    def enrich_message_with_projects(self, text: str) -> str:
        """
        Найти релевантные проекты в тексте по ключевым словам и вернуть их описание.
        
        Args:
            text: Текст сообщения для анализа
            
        Returns:
            Строка с описанием найденных проектов или пустая строка
        """
        if not text:
            return ""
        
        text_lower = text.lower()
        found_projects = []
        
        # Ищем проекты по ключевым словам
        for project in self.projects:
            keywords = project.get("keywords", [])
            description = project.get("description", "")
            status = project.get("status", "unknown")
            key = project.get("key", "")
            
            # Проверяем наличие ключевых слов в тексте
            found_keywords = []
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    found_keywords.append(keyword)
            
            # Также проверяем сам ключ проекта
            if key and key.lower() in text_lower:
                found_keywords.append(key)
            
            # Если нашли совпадения, добавляем проект
            if found_keywords:
                status_text = f" (Status: {status})" if status != "unknown" else ""
                project_name = key if key else "Unnamed Project"
                project_info = f"- {project_name}{status_text}: {description}"
                found_projects.append(project_info)
        
        if found_projects:
            return "\n".join(found_projects)
        
        return ""
    
    def get_all_projects_context(self) -> str:
        """
        Получить контекст всех активных проектов.
        
        Returns:
            Строка с описанием всех активных проектов
        """
        active_projects = []
        
        for project in self.projects:
            status = project.get("status", "unknown")
            if status == "active":
                description = project.get("description", "")
                key = project.get("key", "")
                project_name = key if key else "Unnamed Project"
                active_projects.append(f"- {project_name}: {description}")
        
        if active_projects:
            return "\n".join(active_projects)
        
        return ""
