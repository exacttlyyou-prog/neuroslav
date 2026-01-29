"""
Сервис для проактивных действий бота: напоминания, опросы, предложения.
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal, get_db
from app.db.models import Task, Meeting, Contact
from app.services.telegram_service import TelegramService
from app.services.ollama_service import OllamaService
from app.config import get_settings


class ProactiveService:
    """Сервис для проактивных действий бота."""
    
    def __init__(self):
        self.settings = get_settings()
        self.telegram = TelegramService()
        self.ollama = OllamaService()
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.check_interval = 300  # Проверка каждые 5 минут
    
    async def start(self):
        """Запускает фоновый процесс проактивных действий."""
        if self.running:
            logger.warning("ProactiveService уже запущен")
            return
        
        try:
            self.running = True
            self.task = asyncio.create_task(self._run_loop())
            logger.info("✅ ProactiveService запущен")
        except Exception as e:
            logger.error(f"❌ Ошибка запуска ProactiveService: {e}")
            self.running = False
    
    async def stop(self):
        """Останавливает фоновый процесс."""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("ProactiveService остановлен")
    
    async def _run_loop(self):
        """Основной цикл проактивных действий."""
        logger.info(f"🔄 ProactiveService начал работу (интервал: {self.check_interval} сек)")
        
        while self.running:
            try:
                # Проверяем дедлайны задач
                await self._check_task_deadlines()
                
                # Проверяем забытые задачи
                await self._check_forgotten_tasks()
                
                # Проверяем время для daily check-in
                await self._check_daily_checkin_time()
                
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("ProactiveService получил сигнал остановки")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле ProactiveService: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_task_deadlines(self):
        """Проверяет дедлайны задач и отправляет напоминания."""
        try:
            async with AsyncSessionLocal() as session:
                # Получаем задачи с дедлайнами в ближайшие 24 часа
                now = datetime.now()
                tomorrow = now + timedelta(days=1)
                
                result = await session.execute(
                    select(Task).where(
                        Task.deadline.isnot(None),
                        Task.deadline >= now,
                        Task.deadline <= tomorrow,
                        Task.status == "pending"
                    )
                )
                upcoming_tasks = result.scalars().all()
                
                for task in upcoming_tasks:
                    if task.deadline:
                        hours_until_deadline = (task.deadline - now).total_seconds() / 3600
                        
                        # Напоминаем за 24, 12, 6, 1 час до дедлайна
                        reminder_hours = [24, 12, 6, 1]
                        
                        for reminder_hour in reminder_hours:
                            if 0 < hours_until_deadline <= reminder_hour:
                                # Проверяем, не отправляли ли уже напоминание
                                if task.notified_at:
                                    last_notification = task.notified_at
                                    hours_since_notification = (now - last_notification).total_seconds() / 3600
                                    if hours_since_notification < reminder_hour:
                                        continue
                                
                                # Отправляем напоминание
                                message = f"⏰ Напоминание о задаче\n\n"
                                message += f"<b>{task.text}</b>\n"
                                message += f"Дедлайн: {task.deadline.strftime('%Y-%m-%d %H:%M')}\n"
                                message += f"Осталось: {int(hours_until_deadline)} часов"
                                
                                try:
                                    await self.telegram.send_notification(message)
                                    
                                    # Обновляем время последнего уведомления
                                    task.notified_at = now
                                    await session.commit()
                                    
                                    logger.info(f"Напоминание о задаче {task.id} отправлено")
                                except Exception as e:
                                    logger.error(f"Ошибка при отправке напоминания: {e}")
                                
                                break
                
        except Exception as e:
            logger.error(f"Ошибка при проверке дедлайнов: {e}")
    
    async def _check_forgotten_tasks(self):
        """Проверяет забытые задачи (без активности более 7 дней)."""
        try:
            async with AsyncSessionLocal() as session:
                # Задачи без обновлений более 7 дней
                week_ago = datetime.now() - timedelta(days=7)
                
                result = await session.execute(
                    select(Task).where(
                        Task.status == "pending",
                        Task.created_at <= week_ago
                    )
                )
                forgotten_tasks = result.scalars().all()
                
                if forgotten_tasks:
                    # Формируем сообщение через персону
                    tasks_list = "\n".join([f"- {task.text}" for task in forgotten_tasks[:5]])
                    
                    context = f"Найдено {len(forgotten_tasks)} забытых задач (без активности более 7 дней):\n{tasks_list}"
                    
                    response = await self.ollama.generate_persona_response(
                        user_input="Проверь забытые задачи",
                        context=context
                    )
                    
                    try:
                        await self.telegram.send_notification(
                            f"<b>🔍 Найдены забытые задачи</b>\n\n{response}"
                        )
                        logger.info(f"Уведомление о {len(forgotten_tasks)} забытых задачах отправлено")
                    except Exception as e:
                        logger.error(f"Ошибка при отправке уведомления о забытых задачах: {e}")
                
        except Exception as e:
            logger.error(f"Ошибка при проверке забытых задач: {e}")
    
    async def _check_daily_checkin_time(self):
        """Проверяет время для daily check-in (18:30)."""
        try:
            now = datetime.now()
            checkin_time = now.replace(hour=18, minute=30, second=0, microsecond=0)
            
            # Проверяем, наступило ли время check-in (с допуском ±5 минут)
            if abs((now - checkin_time).total_seconds()) <= 300:  # 5 минут
                # Проверяем, не отправляли ли уже сегодня
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                
                async with AsyncSessionLocal() as session:
                    from app.db.models import DailyCheckin
                    result = await session.execute(
                        select(DailyCheckin).where(
                            DailyCheckin.checkin_date >= today_start,
                            DailyCheckin.status == "sent"
                        )
                    )
                    existing_checkin = result.scalar_one_or_none()
                    
                    if not existing_checkin:
                        # Отправляем daily check-in
                        await self._send_daily_checkin()
                
        except Exception as e:
            logger.error(f"Ошибка при проверке времени check-in: {e}")
    
    async def _send_daily_checkin(self):
        """Отправляет daily check-in всем контактам."""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Contact))
                contacts = result.scalars().all()
                
                if not contacts:
                    logger.info("Нет контактов для отправки daily check-in")
                    return
                
                message = "Что удалось сделать за сегодня?"
                
                sent_count = 0
                for contact in contacts:
                    if contact.telegram_chat_id:
                        try:
                            await self.telegram.send_message_to_user(
                                chat_id=str(contact.telegram_chat_id),
                                message=message
                            )
                            sent_count += 1
                            logger.info(f"Daily check-in отправлен {contact.name}")
                        except Exception as e:
                            logger.warning(f"Не удалось отправить check-in {contact.name}: {e}")
                
                logger.info(f"Daily check-in отправлен {sent_count} контактам")
                
        except Exception as e:
            logger.error(f"Ошибка при отправке daily check-in: {e}")
    
    async def send_suggestions(self, context: str) -> None:
        """
        Отправляет предложения и рекомендации на основе контекста.
        
        Args:
            context: Контекст для генерации предложений
        """
        try:
            prompt = f"""На основе следующего контекста предложи 2-3 конкретных действия для улучшения продуктивности.
            
Контекст:
{context}

Предложения должны быть краткими и конкретными."""
            
            suggestions = await self.ollama.summarize_text(prompt, max_length=300)
            
            message = f"💡 <b>Предложения:</b>\n\n{suggestions}"
            
            await self.telegram.send_notification(message)
            logger.info("Предложения отправлены")
            
        except Exception as e:
            logger.error(f"Ошибка при отправке предложений: {e}")


# Глобальный экземпляр сервиса
_proactive_service: Optional[ProactiveService] = None


def get_proactive_service() -> ProactiveService:
    """Получает глобальный экземпляр ProactiveService."""
    global _proactive_service
    if _proactive_service is None:
        _proactive_service = ProactiveService()
    return _proactive_service
