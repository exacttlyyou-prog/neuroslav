"""
Асинхронный клиент для работы с Firestore.
"""
try:
    from google.cloud.firestore_v1.async_client import AsyncClient
except ImportError:
    # Fallback для старых версий
    from google.cloud import firestore
    AsyncClient = firestore.AsyncClient

from loguru import logger
from uuid import UUID
from datetime import datetime

from core.config import get_settings
from core.schemas import AnalysisSession, MeetingAnalysis


class FirestoreClient:
    """Клиент для работы с Firestore."""
    
    def __init__(self):
        settings = get_settings()
        try:
            self.client = AsyncClient(project=settings.gcp_project_id)
        except TypeError:
            # Альтернативный способ инициализации
            self.client = AsyncClient()
        self.collection = settings.firestore_collection
    
    async def create_session(
        self,
        session: AnalysisSession
    ) -> None:
        """
        Создает новую сессию в Firestore.
        
        Args:
            session: Объект сессии
        """
        try:
            doc_ref = self.client.collection(self.collection).document(str(session.session_id))
            await doc_ref.set(session.model_dump(mode='json'))
            logger.info(f"Создана сессия {session.session_id} в Firestore")
        except Exception as e:
            logger.error(f"Ошибка при создании сессии в Firestore: {e}")
            raise
    
    async def get_session(self, session_id: UUID) -> AnalysisSession | None:
        """
        Получает сессию из Firestore.
        
        Args:
            session_id: ID сессии
            
        Returns:
            Объект сессии или None
        """
        try:
            doc_ref = self.client.collection(self.collection).document(str(session_id))
            doc = await doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                return AnalysisSession.model_validate(data)
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при получении сессии {session_id} из Firestore: {e}")
            raise
    
    async def update_session(
        self,
        session_id: UUID,
        analysis: MeetingAnalysis | None = None,
        status: str | None = None,
        telegram_message_id: int | None = None
    ) -> None:
        """
        Обновляет сессию в Firestore.
        
        Args:
            session_id: ID сессии
            analysis: Опционально, результат анализа
            status: Опционально, новый статус
            telegram_message_id: Опционально, ID сообщения в Telegram
        """
        try:
            doc_ref = self.client.collection(self.collection).document(str(session_id))
            update_data = {"updated_at": datetime.utcnow()}
            
            if analysis:
                update_data["analysis"] = analysis.model_dump(mode='json')
            
            if status:
                update_data["status"] = status
            
            if telegram_message_id is not None:
                update_data["telegram_message_id"] = telegram_message_id
            
            await doc_ref.update(update_data)
            logger.info(f"Обновлена сессия {session_id} в Firestore")
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении сессии {session_id} в Firestore: {e}")
            raise
    
    async def close(self):
        """Закрывает соединение с Firestore."""
        await self.client.close()

