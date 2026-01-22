"""
Streamlit приложение - личный кабинет для работы с нейро-копией.
Аутентификация -> Генерация отчета -> Отправка в Telegram.
"""
import streamlit as st
import asyncio
from datetime import datetime
from typing import Optional
from loguru import logger
from uuid import uuid4

from core.config import get_settings
from core.context_loader import ContextLoader
from core.ai_service import OllamaClient
from core.rag_service import LocalRAG
from core.schemas import MeetingAnalysis
from services.telegram_service import TelegramService


# Простая аутентификация (для личного кабинета)
ADMIN_PASSWORD = "admin"  # Можно вынести в .env


def check_password():
    """Проверка пароля для входа."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        st.title("🔐 Личный кабинет")
        st.markdown("Войдите для работы с нейро-копией")
        
        password = st.text_input("Пароль", type="password", key="password_input")
        
        if st.button("Войти", type="primary", use_container_width=True):
            if password == ADMIN_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Неверный пароль")
        
        st.stop()
    
    return True


# Инициализация сервисов (кэшируется)
@st.cache_resource
def init_services():
    """Инициализация всех сервисов."""
    settings = get_settings()
    context_loader = ContextLoader()
    rag_service = LocalRAG()
    ai_service = OllamaClient(context_loader=context_loader)
    
    # Telegram сервис
    try:
        telegram_service = TelegramService(ai_service=ai_service)
    except Exception as e:
        logger.warning(f"Telegram сервис не инициализирован: {e}")
        telegram_service = None
    
    return context_loader, rag_service, ai_service, telegram_service, settings


async def load_context(context_loader: ContextLoader):
    """Загружает контекст из Notion."""
    try:
        await context_loader.sync_context_from_notion()
        return True, len(context_loader.people), len(context_loader.projects)
    except Exception as e:
        logger.error(f"Ошибка загрузки контекста: {e}")
        return False, len(context_loader.people), len(context_loader.projects)


async def generate_and_send_report(
    transcription: str,
    context_loader: ContextLoader,
    rag_service: LocalRAG,
    ai_service: OllamaClient,
    telegram_service: Optional[TelegramService]
) -> tuple[Optional[MeetingAnalysis], Optional[str]]:
    """
    Генерирует отчет и отправляет в Telegram.
    
    Returns:
        (analysis, error_message)
    """
    try:
        # 1. Сверяемся с базой знаний (RAG)
        logger.info("🔍 Поиск похожих встреч в базе знаний...")
        similar_meetings = rag_service.search_similar(transcription, n_results=3)
        context_texts = []
        for meeting in similar_meetings:
            context_texts.append(
                f"Саммари: {meeting.get('summary', '')}\nЗадачи: {meeting.get('action_items', '')}"
            )
        
        # 2. Анализируем через AI (нейро-копия)
        logger.info("🧠 Анализ через нейро-копию...")
        analysis = await ai_service.analyze_meeting(
            content=transcription,
            context=context_texts,
            response_schema=MeetingAnalysis,
            sender_username=None
        )
        
        # 3. Отправляем в Telegram от лица бота
        if telegram_service:
            logger.info("📤 Отправка отчета в Telegram...")
            session_id = uuid4()
            try:
                message_id = await telegram_service.send_analysis_notification(
                    session_id=session_id,
                    analysis=analysis,
                    notion_page_url=None
                )
                logger.info(f"✅ Отчет отправлен в Telegram, message_id: {message_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки в Telegram: {e}")
                return analysis, f"Отчет сгенерирован, но не отправлен в Telegram: {e}"
        else:
            logger.warning("Telegram сервис не настроен, пропускаем отправку")
            return analysis, "Telegram не настроен (отчет сгенерирован локально)"
        
        return analysis, None
        
    except Exception as e:
        logger.error(f"Ошибка генерации отчета: {e}")
        return None, str(e)


def main():
    """Главная функция Streamlit приложения."""
    st.set_page_config(
        page_title="Нейро-копия | Личный кабинет",
        page_icon="🤖",
        layout="wide"
    )
    
    # Проверка аутентификации
    check_password()
    
    # Инициализация сервисов
    context_loader, rag_service, ai_service, telegram_service, settings = init_services()
    
    # Сайдбар
    with st.sidebar:
        st.header("🤖 Нейро-копия")
        
        # Кнопка выхода
        if st.button("🚪 Выйти", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()
        
        st.divider()
        
        # Загрузка контекста
        st.subheader("📊 Контекст")
        if st.button("🔄 Загрузить контекст", use_container_width=True):
            with st.spinner("Загрузка контекста из Notion..."):
                success, people_count, projects_count = asyncio.run(
                    load_context(context_loader)
                )
                if success:
                    st.success(f"✅ Контекст загружен: {people_count} сотрудников, {projects_count} проектов")
                else:
                    st.warning(f"⚠️ Загружено из кэша: {people_count} сотрудников, {projects_count} проектов")
        
        # Статус контекста
        st.info(f"**Статус:** {len(context_loader.people)} сотрудников, {len(context_loader.projects)} проектов")
        
        st.divider()
        
        # Информация о настройках
        st.caption("**Настройки:**")
        st.caption(f"Модель: {settings.ollama_model}")
        if telegram_service:
            st.caption("✅ Telegram настроен")
        else:
            st.caption("⚠️ Telegram не настроен")
    
    # Главное окно
    st.title("🤖 Генератор минуток")
    st.markdown("Вставьте транскрипцию встречи. Система сверяется с базой знаний и отправляет отчет в Telegram.")
    
    # Поле ввода транскрипции
    transcription = st.text_area(
        "Вставьте текст транскрипции сюда",
        height=300,
        placeholder="Вставьте текст транскрипции встречи..."
    )
    
    # Кнопка генерации и отправки
    if st.button("🚀 Сгенерировать и отправить в Telegram", type="primary", use_container_width=True):
        if not transcription or len(transcription.strip()) < 50:
            st.error("❌ Транскрипция слишком короткая. Минимум 50 символов.")
        else:
            with st.spinner("🧠 Анализирую встречу, сверяюсь с базой знаний и отправляю в Telegram..."):
                analysis, error = asyncio.run(
                    generate_and_send_report(
                        transcription, 
                        context_loader, 
                        rag_service, 
                        ai_service,
                        telegram_service
                    )
                )
                
                if analysis:
                    st.session_state['analysis'] = analysis
                    st.session_state['transcription'] = transcription
                    if error:
                        st.warning(f"⚠️ {error}")
                    else:
                        st.success("✅ Отчет сгенерирован и отправлен в Telegram!")
                else:
                    st.error(f"❌ Ошибка при генерации отчета: {error}")
    
    # Вывод результата (если есть)
    if 'analysis' in st.session_state:
        st.divider()
        st.header("📄 Результат анализа")
        
        analysis = st.session_state['analysis']
        
        # Саммари (HTML)
        st.markdown("### Саммари")
        st.markdown(analysis.summary_md, unsafe_allow_html=True)
        
        # Задачи
        if analysis.action_items:
            st.markdown("### Задачи")
            for i, item in enumerate(analysis.action_items, 1):
                priority_emoji = {'High': '🔴', 'Medium': '🟡', 'Low': '🟢'}.get(item.priority, '⚪')
                assignee_text = f" — {item.assignee}" if item.assignee else ""
                st.markdown(f"{i}. {priority_emoji} **{item.text}**{assignee_text}")
        
        # Риски
        if analysis.risk_assessment:
            st.markdown("### ⚠️ Риски")
            st.warning(analysis.risk_assessment)
        
        st.info("💡 Отчет отправлен в Telegram. Проверьте бота.")


if __name__ == "__main__":
    main()
