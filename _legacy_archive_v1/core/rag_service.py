"""
RAG сервис для работы с ChromaDB (локальная векторная база данных).
Использует sentence-transformers для эмбеддингов.
"""
import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger
from typing import List, Dict, Any
from pathlib import Path

from core.config import get_settings
from core.schemas import ActionItem

# Ленивый импорт sentence_transformers (загружается только при инициализации)
SentenceTransformer = None


class LocalRAG:
    """Локальный RAG сервис на базе ChromaDB."""
    
    def __init__(self):
        settings = get_settings()
        
        # Инициализация ChromaDB
        persist_dir = Path(settings.chroma_persist_dir)
        persist_dir.mkdir(exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        
        # Коллекция для встреч
        self.meetings_collection = self.client.get_or_create_collection(
            name="meetings",
            metadata={"description": "Одобренные анализы встреч"}
        )
        
        # Коллекция для знаний из сообщений
        self.knowledge_collection = self.client.get_or_create_collection(
            name="knowledge",
            metadata={"description": "Знания из входящих сообщений"}
        )
        
        # Загрузка модели для эмбеддингов (ленивый импорт)
        try:
            from sentence_transformers import SentenceTransformer as ST
            logger.info("Загрузка модели sentence-transformers...")
            self.embedding_model = ST('all-MiniLM-L6-v2')
            logger.info("Модель загружена")
        except ImportError:
            logger.error("sentence-transformers не установлен. Установите: pip install sentence-transformers")
            raise ImportError(
                "sentence-transformers не установлен. "
                "Установите: pip install sentence-transformers"
            )
    
    def _get_embedding(self, text: str) -> List[float]:
        """Получить эмбеддинг текста."""
        return self.embedding_model.encode(text).tolist()
    
    def search_similar(self, text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Поиск похожих встреч по вектору.
        
        Args:
            text: Текст для поиска
            n_results: Количество результатов
            
        Returns:
            Список словарей с полями: text, summary, action_items, metadata
        """
        try:
            query_embedding = self._get_embedding(text)
            
            results = self.meetings_collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )
            
            similar_meetings = []
            if results['ids'] and len(results['ids'][0]) > 0:
                for i, meeting_id in enumerate(results['ids'][0]):
                    idx = results['ids'][0].index(meeting_id)
                    similar_meetings.append({
                        'id': meeting_id,
                        'text': results['documents'][0][idx] if results['documents'] else '',
                        'summary': results['metadatas'][0][idx].get('summary', '') if results['metadatas'] else '',
                        'action_items': results['metadatas'][0][idx].get('action_items', '') if results['metadatas'] else '',
                        'distance': results['distances'][0][idx] if results['distances'] else 1.0
                    })
            
            logger.info(f"Найдено {len(similar_meetings)} похожих встреч")
            return similar_meetings
            
        except Exception as e:
            logger.error(f"Ошибка при поиске похожих встреч: {e}")
            return []
    
    def save_approved(
        self,
        meeting_text: str,
        summary: str,
        action_items: List[ActionItem]
    ) -> str:
        """
        Сохранить одобренный анализ встречи в ChromaDB.
        
        Args:
            meeting_text: Текст транскрипции встречи
            summary: Саммари встречи
            action_items: Список задач
            
        Returns:
            ID сохраненной записи
        """
        try:
            import uuid
            from datetime import datetime
            
            meeting_id = str(uuid.uuid4())
            
            # Формируем текст для индексации (транскрипция + саммари)
            indexed_text = f"{meeting_text}\n\n{summary}"
            
            # Сериализуем action_items
            action_items_json = [
                {
                    'text': item.text,
                    'assignee': item.assignee,
                    'priority': item.priority
                }
                for item in action_items
            ]
            
            # Получаем эмбеддинг
            embedding = self._get_embedding(indexed_text)
            
            # Сохраняем в ChromaDB
            self.meetings_collection.add(
                ids=[meeting_id],
                embeddings=[embedding],
                documents=[indexed_text],
                metadatas=[{
                    'summary': summary,
                    'action_items': str(action_items_json),
                    'created_at': datetime.utcnow().isoformat(),
                    'count_action_items': len(action_items)
                }]
            )
            
            logger.info(f"Сохранен одобренный анализ встречи: {meeting_id}")
            return meeting_id
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении одобренного анализа: {e}")
            raise
    
    def save_knowledge(self, text: str, summary: str) -> str:
        """
        Сохранить знание из входящего сообщения в ChromaDB.
        
        Args:
            text: Исходный текст сообщения
            summary: Краткое саммари
            
        Returns:
            ID сохраненной записи
        """
        try:
            import uuid
            from datetime import datetime
            
            knowledge_id = str(uuid.uuid4())
            
            # Формируем текст для индексации
            indexed_text = f"{text}\n\n{summary}"
            
            # Получаем эмбеддинг
            embedding = self._get_embedding(indexed_text)
            
            # Сохраняем в ChromaDB
            self.knowledge_collection.add(
                ids=[knowledge_id],
                embeddings=[embedding],
                documents=[indexed_text],
                metadatas=[{
                    'summary': summary,
                    'created_at': datetime.utcnow().isoformat()
                }]
            )
            
            logger.info(f"Сохранено знание: {knowledge_id}")
            return knowledge_id
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении знания: {e}")
            raise

