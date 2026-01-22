"""
Сервис для разрешения пользователей Telegram по contacts.json.
"""
import json
from pathlib import Path
from loguru import logger
from typing import Dict, Any

# Импорт telegram с fallback
try:
    from telegram import User
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    # Создаем заглушку для User
    class User:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)


class ContactsService:
    """Сервис для работы с контактами пользователей."""
    
    def __init__(self, contacts_file: str = "contacts.json"):
        """
        Инициализация сервиса контактов.
        
        Args:
            contacts_file: Путь к файлу contacts.json
        """
        self.contacts_file = Path(contacts_file)
        self.contacts: Dict[str, Dict[str, str]] = {}
        self._load_contacts()
    
    def _load_contacts(self):
        """Загрузить контакты из JSON файла."""
        try:
            if self.contacts_file.exists():
                with open(self.contacts_file, 'r', encoding='utf-8') as f:
                    self.contacts = json.load(f)
                logger.info(f"Загружено {len(self.contacts)} контактов из {self.contacts_file}")
            else:
                logger.warning(f"Файл {self.contacts_file} не найден, используем пустую базу")
                self.contacts = {}
        except Exception as e:
            logger.error(f"Ошибка при загрузке контактов: {e}")
            self.contacts = {}
    
    def resolve_user(self, telegram_user: User) -> Dict[str, str]:
        """
        Разрешить пользователя Telegram по username или first_name.
        
        Args:
            telegram_user: Объект User из Telegram
            
        Returns:
            Словарь с полями: name, role
        """
        # Пытаемся найти по username
        if telegram_user.username:
            username_lower = telegram_user.username.lower()
            if username_lower in self.contacts:
                contact = self.contacts[username_lower]
                return {
                    "name": contact.get("name", telegram_user.first_name or "Unknown"),
                    "role": contact.get("role", "Unknown")
                }
        
        # Пытаемся найти по first_name (точное совпадение)
        if telegram_user.first_name:
            first_name_lower = telegram_user.first_name.lower()
            for username, contact in self.contacts.items():
                if contact.get("name", "").lower() == first_name_lower:
                    return {
                        "name": contact.get("name", telegram_user.first_name),
                        "role": contact.get("role", "Unknown")
                    }
        
        # Если не найдено, возвращаем дефолтные значения
        return {
            "name": telegram_user.first_name or "Unknown",
            "role": "Unknown"
        }

