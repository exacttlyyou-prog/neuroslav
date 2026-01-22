"""
RAG сервис для работы с ChromaDB (локальная векторная база данных).
Использует sentence-transformers для эмбеддингов.
"""
import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.config import get_settings


class RAGService:
    """Локальный RAG сервис на базе ChromaDB."""
    
    def __init__(self):
        settings = get_settings()
        
        # Инициализация ChromaDB
        persist_dir = Path(settings.chroma_persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        
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
        
        # Коллекция для задач
        self.tasks_collection = self.client.get_or_create_collection(
            name="tasks",
            metadata={"description": "Задачи и напоминания"}
        )
        
        # Загрузка модели для эмбеддингов
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Загрузка модели sentence-transformers...")
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
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
    
    async def add_meeting(self, meeting_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Добавляет встречу в векторную БД.
        
        Args:
            meeting_id: Уникальный ID встречи
            content: Текст встречи
            metadata: Дополнительные метаданные
        """
        try:
            embedding = self._get_embedding(content)
            metadata = metadata or {}
            metadata["meeting_id"] = meeting_id
            
            self.meetings_collection.add(
                ids=[meeting_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
            )
            
            logger.info(f"Встреча {meeting_id} добавлена в RAG")
        except Exception as e:
            logger.error(f"Ошибка при добавлении встречи в RAG: {e}")
            raise
    
    async def search_similar_meetings(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Ищет похожие встречи.
        
        Args:
            query: Текст запроса
            limit: Количество результатов
            
        Returns:
            Список похожих встреч
        """
        try:
            query_embedding = self._get_embedding(query)
            
            results = self.meetings_collection.query(
                query_embeddings=[query_embedding],
                n_results=limit
            )
            
            similar_meetings = []
            if results.get("documents") and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    similar_meetings.append({
                        "content": doc,
                        "metadata": results.get("metadatas", [[]])[0][i] if results.get("metadatas") else {},
                        "distance": results.get("distances", [[]])[0][i] if results.get("distances") else None
                    })
            
            logger.info(f"Найдено {len(similar_meetings)} похожих встреч")
            return similar_meetings
        except Exception as e:
            logger.error(f"Ошибка при поиске похожих встреч: {e}")
            return []
    
    async def add_knowledge(self, doc_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Добавляет документ в базу знаний.
        
        Args:
            doc_id: Уникальный ID документа
            content: Текст документа
            metadata: Дополнительные метаданные
        """
        try:
            embedding = self._get_embedding(content)
            metadata = metadata or {}
            metadata["doc_id"] = doc_id
            
            self.knowledge_collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
            )
            
            logger.info(f"Документ {doc_id} добавлен в базу знаний")
        except Exception as e:
            logger.error(f"Ошибка при добавлении документа в базу знаний: {e}")
            raise
    
    async def search_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Ищет в базе знаний.
        
        Args:
            query: Текст запроса
            limit: Количество результатов
            
        Returns:
            Список релевантных документов
        """
        try:
            query_embedding = self._get_embedding(query)
            
            results = self.knowledge_collection.query(
                query_embeddings=[query_embedding],
                n_results=limit
            )
            
            knowledge_items = []
            if results.get("documents") and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    knowledge_items.append({
                        "content": doc,
                        "metadata": results.get("metadatas", [[]])[0][i] if results.get("metadatas") else {},
                        "score": 1 - (results.get("distances", [[]])[0][i] if results.get("distances") else 1.0)
                    })
            
            logger.info(f"Найдено {len(knowledge_items)} релевантных документов")
            return knowledge_items
        except Exception as e:
            logger.error(f"Ошибка при поиске в базе знаний: {e}")
            return []
    
    async def add_task(self, task_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Добавляет задачу в векторную БД.
        
        Args:
            task_id: Уникальный ID задачи
            content: Текст задачи
            metadata: Дополнительные метаданные
        """
        try:
            embedding = self._get_embedding(content)
            metadata = metadata or {}
            metadata["task_id"] = task_id
            
            self.tasks_collection.add(
                ids=[task_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
            )
            
            logger.info(f"Задача {task_id} добавлена в RAG")
        except Exception as e:
            logger.error(f"Ошибка при добавлении задачи в RAG: {e}")
            raise
    
    async def search_similar_tasks(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Ищет похожие задачи.
        
        Args:
            query: Текст запроса
            limit: Количество результатов
            
        Returns:
            Список похожих задач
        """
        try:
            query_embedding = self._get_embedding(query)
            
            results = self.tasks_collection.query(
                query_embeddings=[query_embedding],
                n_results=limit
            )
            
            similar_tasks = []
            if results.get("documents") and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    similar_tasks.append({
                        "content": doc,
                        "metadata": results.get("metadatas", [[]])[0][i] if results.get("metadatas") else {},
                        "distance": results.get("distances", [[]])[0][i] if results.get("distances") else None
                    })
            
            logger.info(f"Найдено {len(similar_tasks)} похожих задач")
            return similar_tasks
        except Exception as e:
            logger.error(f"Ошибка при поиске похожих задач: {e}")
            return []
