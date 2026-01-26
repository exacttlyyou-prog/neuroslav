"""
Сервис для загрузки и работы с контекстом людей, проектов и глоссария из Notion баз данных.
Кэширует данные в памяти для быстрого доступа.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from loguru import logger
import httpx
from difflib import SequenceMatcher

from app.config import get_settings


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
        self.glossary: Dict[str, str] = {}
        
        # Обратный индекс для поиска по всем вариантам имен (алиасам)
        self.people_lookup_map: Dict[str, Dict[str, str]] = {}
        self.projects_lookup_map: Dict[str, Dict[str, Any]] = {}
        
        # Notion сервис будет инициализирован при необходимости
        self.notion_service = None
        
        # Загружаем только JSON fallback при инициализации (синхронно)
        self._load_from_json()
        # Строим обратный индекс после загрузки JSON
        self._build_lookup_maps()
        
        # Флаги для отслеживания синхронизации с Notion
        self._notion_synced = False
        self._preload_started = False
    
    async def ensure_notion_sync(self):
        """Обеспечивает синхронизацию с Notion при первом обращении."""
        if not self._notion_synced:
            try:
                await self.sync_context_from_notion()
                logger.info("✅ Автоматическая синхронизация с Notion завершена")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось синхронизироваться с Notion: {e}")
                logger.info("Используем данные из JSON файлов как fallback")
    
    async def preload_context(self):
        """
        Предзагружает контекст в фоновом режиме для оптимизации скорости.
        Вызывается при старте приложения.
        """
        if self._preload_started:
            return
            
        self._preload_started = True
        logger.info("🔄 Начинаем предзагрузку контекста...")
        
        try:
            # Асинхронно синхронизируемся с Notion
            await self.ensure_notion_sync()
            
            # Предварительно строим поисковые индексы
            self._build_lookup_maps()
            
            logger.info(f"✅ Предзагрузка контекста завершена: {len(self.people)} людей, {len(self.projects)} проектов")
            
        except Exception as e:
            logger.error(f"❌ Ошибка предзагрузки контекста: {e}")
            # Fallback на JSON данные если что-то пошло не так
            self._load_from_json()
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
                    if isinstance(projects_data, dict):
                        normalized = []
                        for key, data in projects_data.items():
                            if isinstance(data, dict):
                                normalized.append({"key": key, **data})
                            else:
                                normalized.append({"key": key, "description": str(data)})
                        self.projects = normalized
                    elif isinstance(projects_data, list):
                        self.projects = projects_data
                    else:
                        self.projects = []
                logger.info(f"Загружено {len(self.projects)} проектов из {projects_file}")
            else:
                logger.warning(f"Файл {projects_file} не найден")
                self.projects = []
        except Exception as e:
            logger.error(f"Ошибка при загрузке projects.json: {e}")
            self.projects = []
    
    def _build_lookup_maps(self):
        """Построить обратные индексы для поиска по алиасам."""
        # Индекс для людей
        self.people_lookup_map = {}
        for username_lower, person_data in self.people.items():
            name = person_data.get('name', '')
            aliases = person_data.get('aliases', [])
            
            # Добавляем основное имя
            if name:
                self.people_lookup_map[name.lower()] = person_data
            
            # Добавляем алиасы
            for alias in aliases:
                if alias:
                    self.people_lookup_map[alias.lower()] = person_data
        
        # Индекс для проектов
        self.projects_lookup_map = {}
        for project in self.projects:
            if not isinstance(project, dict):
                continue
            key = project.get('key', '').lower()
            keywords = project.get('keywords', [])
            
            if key:
                self.projects_lookup_map[key] = project
            
            for keyword in keywords:
                if keyword:
                    self.projects_lookup_map[keyword.lower()] = project
        
        logger.info(f"Построен обратный индекс для {len(self.people_lookup_map)} вариантов имен людей")
        logger.info(f"Построен обратный индекс для {len(self.projects_lookup_map)} вариантов названий проектов")
    
    async def sync_context_from_notion(self):
        """
        Синхронизировать контекст из Notion баз данных.
        Загружает данные и кэширует в памяти.
        """
        # Ленивая инициализация Notion сервиса
        if not self.notion_service:
            try:
                from app.services.notion_service import NotionService
                self.notion_service = NotionService()
            except Exception as e:
                logger.warning(f"Notion сервис недоступен: {e}, используем только JSON fallback")
                return
        
        logger.info("Синхронизация контекста из Notion...")
        
        # ПОЛНАЯ ЗАМЕНА данных из Notion (не дополнение к JSON)
        # Очищаем старые данные для обеспечения актуальности
        self.people = {}
        self.projects = []
        self.glossary = {}
        
        # Загружаем контакты из Notion
        contacts = await self.notion_service.get_contacts_from_db()
        notion_people_count = 0
        for contact in contacts:
            username = contact.get('telegram_username', '').lower()
            name = contact.get('name', '')
            
            # Добавляем по username если есть
            if username:
                self.people[username] = {
                    'id': contact.get('id'),  # Notion page ID для поиска в БД
                    'name': name,
                    'role': contact.get('role', ''),
                    'context': contact.get('context', ''),
                    'telegram_username': contact.get('telegram_username', ''),
                    'aliases': contact.get('aliases', []),
                    'source': 'notion'  # Помечаем источник
                }
                notion_people_count += 1
            
            # ДОПОЛНИТЕЛЬНО: Добавляем по имени для лучшего поиска
            if name and name.lower() not in self.people:
                self.people[name.lower()] = {
                    'id': contact.get('id'),
                    'name': name,
                    'role': contact.get('role', ''),
                    'context': contact.get('context', ''),
                    'telegram_username': contact.get('telegram_username', ''),
                    'aliases': contact.get('aliases', []),
                    'source': 'notion'
                }
                notion_people_count += 1
        
        # Если не получили данные из Notion, используем JSON как fallback
        if notion_people_count == 0:
            logger.warning("⚠️ Не получены данные о людях из Notion, используем JSON fallback")
            self._load_people_json()
        else:
            logger.info(f"✅ Загружено {notion_people_count} записей о людях из Notion")
        
        # Загружаем проекты из Notion
        projects = await self.notion_service.get_projects_from_db()
        if projects:
            self.projects = projects
            for project in self.projects:
                project['source'] = 'notion'  # Помечаем источник
            logger.info(f"✅ Загружено {len(projects)} проектов из Notion")
        else:
            logger.warning("⚠️ Не получены данные о проектах из Notion, используем JSON fallback")
            self._load_projects_json()
        
        # Загружаем глоссарий из Notion
        glossary = await self.notion_service.get_glossary_from_db()
        if glossary:
            self.glossary = glossary
            logger.info(f"✅ Загружено {len(glossary)} терминов из Notion глоссария")
        else:
            logger.warning("⚠️ Глоссарий из Notion недоступен, используем пустой")
        
        logger.info(f"Синхронизация завершена: {len(self.people)} людей, {len(self.projects)} проектов, {len(self.glossary)} терминов")
        
        # Перестраиваем индексы после синхронизации
        self._build_lookup_maps()
        self._notion_synced = True
    
    def get_person_context(self, username: str) -> Optional[str]:
        """
        Получить контекст человека по username.
        
        Args:
            username: Telegram username (без @)
            
        Returns:
            Строка с контекстом или None
        """
        username_lower = username.lower().lstrip('@')
        person = self.people.get(username_lower)
        if person:
            context = person.get('context', '')
            role = person.get('role', '')
            if context or role:
                return f"{role}: {context}" if role else context
        return None
    
    def _fuzzy_match(self, query: str, candidates: List[str], threshold: float = 0.6) -> List[Tuple[str, float]]:
        """
        Fuzzy matching строки с кандидатами.
        
        Args:
            query: Строка для поиска
            candidates: Список кандидатов
            threshold: Минимальный порог схожести (0.0-1.0)
            
        Returns:
            Список кортежей (кандидат, score) отсортированных по убыванию score
        """
        query_lower = query.lower()
        matches = []
        
        for candidate in candidates:
            candidate_lower = candidate.lower()
            # Используем SequenceMatcher для вычисления схожести
            ratio = SequenceMatcher(None, query_lower, candidate_lower).ratio()
            
            # Также проверяем частичное совпадение (если query содержится в candidate или наоборот)
            if query_lower in candidate_lower or candidate_lower in query_lower:
                ratio = max(ratio, 0.8)  # Повышаем score для частичных совпадений
            
            if ratio >= threshold:
                matches.append((candidate, ratio))
        
        # Сортируем по убыванию score
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches
    
    async def resolve_entity(self, text: str, use_fuzzy: bool = True, fuzzy_threshold: float = 0.6) -> Dict[str, List[Dict[str, Any]]]:
        """
        Умный поиск людей и проектов в тексте с поддержкой fuzzy matching.
        Автоматически синхронизируется с Notion при первом вызове.
        
        Args:
            text: Текст для анализа
            use_fuzzy: Использовать ли fuzzy matching
            fuzzy_threshold: Порог схожести для fuzzy matching (0.0-1.0)
            
        Returns:
            Словарь с ключами 'people' и 'projects'
        """
        # Автоматическая синхронизация с Notion при первом использовании
        await self.ensure_notion_sync()
        found_people = []
        found_projects = []
        
        text_lower = text.lower()
        text_words = text_lower.split()
        
        # Точный поиск людей
        for alias_lower, person_data in self.people_lookup_map.items():
            if alias_lower in text_lower:
                # Проверяем, что это не дубликат
                if person_data not in found_people:
                    found_people.append(person_data)
        
        # Fuzzy matching для людей (если включено)
        if use_fuzzy:
            # Извлекаем потенциальные имена из текста (слова с заглавной буквы или после определенных паттернов)
            potential_names = []
            for word in text_words:
                if len(word) > 2:  # Игнорируем короткие слова
                    potential_names.append(word)
            
            # Для каждого потенциального имени ищем совпадения
            for name in potential_names:
                if len(name) < 3:
                    continue
                
                # Получаем список всех кандидатов (алиасов)
                candidates = list(self.people_lookup_map.keys())
                matches = self._fuzzy_match(name, candidates, fuzzy_threshold)
                
                # Добавляем найденные совпадения
                for matched_alias, score in matches[:3]:  # Берем топ-3 совпадения
                    person_data = self.people_lookup_map[matched_alias]
                    if person_data not in found_people:
                        # Добавляем информацию о score для отладки
                        person_with_score = person_data.copy()
                        person_with_score['_match_score'] = score
                        person_with_score['_matched_name'] = name
                        found_people.append(person_with_score)
        
        # Поиск проектов (точный)
        for keyword_lower, project_data in self.projects_lookup_map.items():
            if keyword_lower in text_lower:
                if project_data not in found_projects:
                    found_projects.append(project_data)
        
        # Fuzzy matching для проектов (если включено)
        if use_fuzzy:
            for word in text_words:
                if len(word) < 3:
                    continue
                
                candidates = list(self.projects_lookup_map.keys())
                matches = self._fuzzy_match(word, candidates, fuzzy_threshold)
                
                for matched_keyword, score in matches[:3]:
                    project_data = self.projects_lookup_map[matched_keyword]
                    if project_data not in found_projects:
                        project_with_score = project_data.copy()
                        project_with_score['_match_score'] = score
                        found_projects.append(project_with_score)
        
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
        for term, definition in self.glossary.items():
            term_lower = term.lower()
            # Проверяем, что термин достаточно длинный и встречается в тексте
            if len(term_lower) > 2 and term_lower in text_lower:
                found_terms[term] = definition
        
        return found_terms
    
    def _load_people_json(self):
        """Загружает людей из JSON файла как fallback."""
        try:
            people_path = os.path.join(os.path.dirname(__file__), "..", "data", "people.json")
            with open(people_path, 'r', encoding='utf-8') as f:
                people_data = json.load(f)
            
            for username, person_info in people_data.items():
                self.people[username.lower()] = person_info
                person_info['source'] = 'json'  # Помечаем источник
                
            logger.info(f"✅ Загружено {len(people_data)} записей о людях из JSON (fallback)")
        except FileNotFoundError:
            logger.warning("Файл people.json не найден")
            self.people = {}
    
    def _load_projects_json(self):
        """Загружает проекты из JSON файла как fallback."""
        try:
            projects_path = os.path.join(os.path.dirname(__file__), "..", "data", "projects.json")
            with open(projects_path, 'r', encoding='utf-8') as f:
                projects_data = json.load(f)
            
            self.projects = projects_data.get('projects', [])
            for project in self.projects:
                project['source'] = 'json'  # Помечаем источник
                
            logger.info(f"✅ Загружено {len(self.projects)} проектов из JSON (fallback)")
        except FileNotFoundError:
            logger.warning("Файл projects.json не найден")
            self.projects = []