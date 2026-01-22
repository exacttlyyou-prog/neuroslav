"""
SQLAlchemy модели для базы данных.
"""
from sqlalchemy import Column, String, Text, DateTime, JSON, Integer
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional

from app.db.database import Base


class Task(Base):
    """Модель задачи."""
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True)
    text = Column(Text, nullable=False)
    intent = Column(Text)  # Извлеченный intent из текста
    deadline = Column(DateTime)
    priority = Column(String)  # High, Medium, Low
    status = Column(String, default="pending")  # pending, scheduled, completed
    created_at = Column(DateTime, server_default=func.now())
    notified_at = Column(DateTime, nullable=True)
    notion_task_id = Column(String, nullable=True)  # ID задачи в Notion


class Meeting(Base):
    """Модель встречи."""
    __tablename__ = "meetings"
    
    id = Column(String, primary_key=True)
    transcript = Column(Text)
    summary = Column(Text)
    participants = Column(JSON)  # Список участников
    projects = Column(JSON)  # Список проектов
    action_items = Column(JSON)  # Список задач из встречи
    draft_message = Column(Text)  # Draft follow-up сообщения
    status = Column(String, default="processing")  # processing, pending_approval, completed, sent
    created_at = Column(DateTime, server_default=func.now())
    notion_page_id = Column(String, nullable=True)  # ID страницы в Notion


class KnowledgeItem(Base):
    """Модель индексированного документа."""
    __tablename__ = "knowledge_items"
    
    id = Column(String, primary_key=True)
    source_file = Column(String, nullable=False)
    file_type = Column(String)
    indexed_at = Column(DateTime, server_default=func.now())
    doc_metadata = Column(JSON)  # Дополнительные метаданные (metadata - зарезервировано SQLAlchemy)
    chunks_count = Column(Integer, default=0)  # Количество чанков


class Contact(Base):
    """Модель контакта (кэш из Notion)."""
    __tablename__ = "contacts"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    telegram_username = Column(String)
    telegram_chat_id = Column(String)  # Chat ID для отправки сообщений
    email = Column(String)
    aliases = Column(JSON)  # Список алиасов
    notion_page_id = Column(String)  # ID страницы в Notion
    last_synced = Column(DateTime, server_default=func.now())


class DailyCheckin(Base):
    """Модель ежедневного опроса."""
    __tablename__ = "daily_checkins"
    
    id = Column(String, primary_key=True)
    contact_id = Column(String, nullable=False)  # ID контакта
    checkin_date = Column(DateTime, nullable=False)  # Дата опроса
    question_sent_at = Column(DateTime)  # Когда отправлен вопрос
    response_received_at = Column(DateTime)  # Когда получен ответ
    response_text = Column(Text)  # Текст ответа
    clarification_asked = Column(Integer, default=0)  # Количество уточнений
    status = Column(String, default="pending")  # pending, sent, responded, completed
    created_at = Column(DateTime, server_default=func.now())
