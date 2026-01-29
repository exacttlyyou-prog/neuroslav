"""
Система безопасности для Digital Twin API.
Включает аутентификацию, авторизацию и мониторинг безопасности.
"""
import hashlib
import secrets
import time
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger

from app.config import get_settings
from app.models.schemas import UserIdentity, SecurityEvent


class SecurityManager:
    """Менеджер безопасности системы."""
    
    def __init__(self):
        self.settings = get_settings()
        self.blocked_ips: Set[str] = set()
        self.suspicious_patterns = [
            r"(?i)(union\s+select|drop\s+table|insert\s+into|delete\s+from)",
            r"(?i)(script\s*>|javascript:|vbscript:)",
            r"(?i)(<script|</script>|<iframe|</iframe>)",
        ]
        self.failed_attempts: Dict[str, List[datetime]] = {}
    
    def generate_api_key(self, prefix: str = "dt_") -> str:
        """Генерирует безопасный API ключ."""
        random_part = secrets.token_urlsafe(32)
        return f"{prefix}{random_part}"
    
    def hash_sensitive_data(self, data: str, salt: str = None) -> str:
        """Хеширует чувствительные данные."""
        if salt is None:
            salt = secrets.token_hex(16)
        
        combined = f"{salt}{data}"
        hashed = hashlib.sha256(combined.encode()).hexdigest()
        return f"{salt}${hashed}"
    
    def verify_hash(self, data: str, hashed: str) -> bool:
        """Проверяет хеш чувствительных данных."""
        try:
            salt, hash_value = hashed.split('$', 1)
            expected = self.hash_sensitive_data(data, salt)
            return secrets.compare_digest(expected, hashed)
        except:
            return False
    
    def is_authorized_chat(self, chat_id: str) -> bool:
        """Проверяет авторизацию Telegram чата."""
        # Разрешенные чаты из конфигурации (нормализуем к str, без пробелов)
        authorized_chats: List[str] = []
        for raw in (self.settings.admin_chat_id, self.settings.ok_chat_id):
            if raw and str(raw).strip():
                authorized_chats.append(str(raw).strip())
        
        # Если чаты не настроены, разрешаем все (режим разработки)
        if not authorized_chats:
            logger.warning("Авторизованные чаты не настроены - разрешен доступ всем")
            return True
        
        c = str(chat_id).strip()
        return c in authorized_chats
    
    def check_suspicious_content(self, text: str) -> List[str]:
        """Проверяет текст на подозрительные паттерны."""
        import re
        found_patterns = []
        
        for pattern in self.suspicious_patterns:
            if re.search(pattern, text):
                found_patterns.append(pattern)
        
        return found_patterns
    
    def log_security_event(
        self,
        event_type: str,
        client_id: str,
        description: str,
        severity: str = "medium",
        context: Dict = None
    ):
        """Логирует событие безопасности."""
        event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            client_id=client_id,
            description=description,
            context=context or {}
        )
        
        logger.warning(
            f"Security event: {event_type}",
            extra={
                "security_event": event.dict(),
                "client_id": client_id
            }
        )
    
    def should_block_client(self, client_id: str) -> bool:
        """Определяет нужно ли заблокировать клиента."""
        # Проверяем IP блокировку
        if client_id in self.blocked_ips:
            return True
        
        # Проверяем частоту неудачных попыток
        if client_id in self.failed_attempts:
            recent_failures = [
                attempt for attempt in self.failed_attempts[client_id]
                if datetime.now() - attempt < timedelta(minutes=15)
            ]
            
            if len(recent_failures) >= 10:  # Более 10 попыток за 15 минут
                return True
        
        return False
    
    def record_failed_attempt(self, client_id: str):
        """Записывает неудачную попытку аутентификации."""
        if client_id not in self.failed_attempts:
            self.failed_attempts[client_id] = []
        
        self.failed_attempts[client_id].append(datetime.now())
        
        # Очищаем старые попытки (старше 1 часа)
        cutoff = datetime.now() - timedelta(hours=1)
        self.failed_attempts[client_id] = [
            attempt for attempt in self.failed_attempts[client_id]
            if attempt > cutoff
        ]
    
    def block_client(self, client_id: str, reason: str):
        """Блокирует клиента."""
        self.blocked_ips.add(client_id)
        self.log_security_event(
            event_type="client_blocked",
            client_id=client_id,
            description=f"Client blocked: {reason}",
            severity="high"
        )
        logger.warning(f"Client blocked: {client_id} - {reason}")


class TelegramAuth:
    """Система аутентификации для Telegram запросов."""
    
    def __init__(self, security_manager: SecurityManager):
        self.security_manager = security_manager
    
    def verify_telegram_webhook(
        self,
        chat_id: str,
        user_identity: Optional[UserIdentity] = None
    ) -> bool:
        """Проверяет авторизацию Telegram webhook."""
        
        # Проверяем блокировку клиента
        if self.security_manager.should_block_client(chat_id):
            self.security_manager.log_security_event(
                event_type="blocked_access_attempt",
                client_id=chat_id,
                description="Attempt to access from blocked client",
                severity="high"
            )
            return False
        
        # Проверяем авторизацию чата
        if not self.security_manager.is_authorized_chat(chat_id):
            self.security_manager.record_failed_attempt(chat_id)
            self.security_manager.log_security_event(
                event_type="unauthorized_chat_access",
                client_id=chat_id,
                description=f"Unauthorized chat attempted access: {chat_id}",
                severity="medium"
            )
            return False
        
        return True
    
    def extract_user_identity(self, telegram_message: Dict) -> UserIdentity:
        """Извлекает идентификационные данные пользователя."""
        chat_info = telegram_message.get('chat', {})
        from_info = telegram_message.get('from', {})
        
        return UserIdentity(
            chat_id=str(chat_info.get('id', '')),
            username=from_info.get('username'),
            first_name=from_info.get('first_name'),
            last_name=from_info.get('last_name')
        )


class APIKeyAuth:
    """Система аутентификации по API ключу для внешних API."""
    
    def __init__(self, security_manager: SecurityManager):
        self.security_manager = security_manager
        self.valid_keys = set()
        
        # Добавляем ключи из конфигурации если есть
        if hasattr(self.security_manager.settings, 'api_keys'):
            self.valid_keys.update(self.security_manager.settings.api_keys or [])
    
    def verify_api_key(self, api_key: str) -> bool:
        """Проверяет валидность API ключа."""
        if not api_key:
            return False
        
        # В режиме разработки разрешаем все
        if not self.valid_keys:
            logger.warning("API keys не настроены - разрешен доступ всем")
            return True
        
        return api_key in self.valid_keys
    
    def add_api_key(self, api_key: str):
        """Добавляет новый API ключ."""
        self.valid_keys.add(api_key)
        logger.info("Добавлен новый API ключ")
    
    def revoke_api_key(self, api_key: str):
        """Отзывает API ключ."""
        self.valid_keys.discard(api_key)
        logger.info("API ключ отозван")


# Глобальные экземпляры
_security_manager: Optional[SecurityManager] = None
_telegram_auth: Optional[TelegramAuth] = None
_api_key_auth: Optional[APIKeyAuth] = None


def get_security_manager() -> SecurityManager:
    """Получает глобальный экземпляр менеджера безопасности."""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager()
    return _security_manager


def get_telegram_auth() -> TelegramAuth:
    """Получает экземпляр Telegram аутентификации."""
    global _telegram_auth
    if _telegram_auth is None:
        _telegram_auth = TelegramAuth(get_security_manager())
    return _telegram_auth


def get_api_key_auth() -> APIKeyAuth:
    """Получает экземпляр API key аутентификации."""
    global _api_key_auth
    if _api_key_auth is None:
        _api_key_auth = APIKeyAuth(get_security_manager())
    return _api_key_auth


# Dependency для FastAPI
security = HTTPBearer(auto_error=False)


async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    """FastAPI dependency для проверки API ключа."""
    if not credentials:
        raise HTTPException(status_code=401, detail="API key required")
    
    auth = get_api_key_auth()
    if not auth.verify_api_key(credentials.credentials):
        # Логируем неудачную попытку
        security_manager = get_security_manager()
        security_manager.log_security_event(
            event_type="invalid_api_key",
            client_id=credentials.credentials[:10] + "...",  # Частично скрываем ключ
            description="Invalid API key used",
            severity="medium"
        )
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return True


def require_telegram_auth(chat_id: str) -> bool:
    """Dependency для проверки Telegram авторизации."""
    auth = get_telegram_auth()
    
    if not auth.verify_telegram_webhook(chat_id):
        raise HTTPException(
            status_code=403,
            detail="Unauthorized chat. This bot is restricted to authorized users only."
        )
    
    return True