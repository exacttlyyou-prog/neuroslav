"""
Сервис для планирования и отложенных действий.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, List
from loguru import logger
from pathlib import Path
import json

from app.config import get_settings


class ScheduledTask:
    """Задача для планировщика."""
    
    def __init__(
        self,
        task_id: str,
        execute_at: datetime,
        action: Callable,
        action_args: Dict[str, Any],
        repeat_interval: Optional[timedelta] = None
    ):
        self.task_id = task_id
        self.execute_at = execute_at
        self.action = action
        self.action_args = action_args
        self.repeat_interval = repeat_interval
        self.last_executed: Optional[datetime] = None
    
    def should_execute(self) -> bool:
        """Проверяет, нужно ли выполнить задачу."""
        return datetime.now() >= self.execute_at
    
    def get_next_execution_time(self) -> Optional[datetime]:
        """Возвращает время следующего выполнения (если задача повторяющаяся)."""
        if self.repeat_interval:
            if self.last_executed:
                return self.last_executed + self.repeat_interval
            return self.execute_at + self.repeat_interval
        return None


class SchedulerService:
    """Сервис для планирования и отложенных действий."""
    
    def __init__(self):
        self.settings = get_settings()
        self.tasks: Dict[str, ScheduledTask] = {}
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.check_interval = 60  # Проверка каждую минуту
        self.storage_path = Path("/tmp/scheduled_tasks.json")
        self._load_tasks()
    
    def _load_tasks(self):
        """Загружает задачи из файла."""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    # Загружаем только невыполненные задачи
                    now = datetime.now()
                    for task_data in data.get("tasks", []):
                        execute_at = datetime.fromisoformat(task_data["execute_at"])
                        if execute_at > now:
                            # Восстанавливаем задачу (без action, так как его нельзя сериализовать)
                            # Action нужно будет восстановить при старте
                            pass
        except Exception as e:
            logger.warning(f"Не удалось загрузить задачи из файла: {e}")
    
    def _save_tasks(self):
        """Сохраняет задачи в файл."""
        try:
            tasks_data = []
            for task in self.tasks.values():
                if task.repeat_interval:  # Сохраняем только повторяющиеся задачи
                    tasks_data.append({
                        "task_id": task.task_id,
                        "execute_at": task.execute_at.isoformat(),
                        "repeat_interval_seconds": task.repeat_interval.total_seconds() if task.repeat_interval else None,
                        "action_args": task.action_args
                    })
            
            with open(self.storage_path, "w") as f:
                json.dump({"tasks": tasks_data}, f)
        except Exception as e:
            logger.warning(f"Не удалось сохранить задачи в файл: {e}")
    
    async def start(self):
        """Запускает планировщик."""
        if self.running:
            logger.warning("SchedulerService уже запущен")
            return
        
        try:
            self.running = True
            self.task = asyncio.create_task(self._run_loop())
            logger.info("✅ SchedulerService запущен")
        except Exception as e:
            logger.error(f"❌ Ошибка запуска SchedulerService: {e}")
            self.running = False
    
    async def stop(self):
        """Останавливает планировщик."""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        self._save_tasks()
        logger.info("SchedulerService остановлен")
    
    async def _run_loop(self):
        """Основной цикл планировщика."""
        logger.info(f"🔄 SchedulerService начал работу (интервал: {self.check_interval} сек)")
        
        while self.running:
            try:
                await self._check_and_execute_tasks()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("SchedulerService получил сигнал остановки")
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле SchedulerService: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_and_execute_tasks(self):
        """Проверяет и выполняет задачи, которые готовы к выполнению."""
        now = datetime.now()
        tasks_to_execute = []
        
        for task_id, task in list(self.tasks.items()):
            if task.should_execute():
                tasks_to_execute.append(task)
        
        for task in tasks_to_execute:
            try:
                logger.info(f"Выполнение запланированной задачи: {task.task_id}")
                await task.action(**task.action_args)
                task.last_executed = now
                
                # Если задача повторяющаяся, планируем следующее выполнение
                if task.repeat_interval:
                    next_time = task.get_next_execution_time()
                    if next_time:
                        task.execute_at = next_time
                        logger.info(f"Следующее выполнение задачи {task.task_id}: {next_time}")
                else:
                    # Удаляем одноразовую задачу
                    del self.tasks[task.task_id]
                    logger.info(f"Задача {task.task_id} выполнена и удалена")
                
            except Exception as e:
                logger.error(f"Ошибка при выполнении задачи {task.task_id}: {e}")
                # Удаляем задачу при ошибке (чтобы не повторять бесконечно)
                if task_id in self.tasks:
                    del self.tasks[task_id]
        
        if tasks_to_execute:
            self._save_tasks()
    
    def schedule_task(
        self,
        task_id: str,
        execute_at: datetime,
        action: Callable,
        action_args: Dict[str, Any],
        repeat_interval: Optional[timedelta] = None
    ) -> bool:
        """
        Планирует задачу на выполнение.
        
        Args:
            task_id: Уникальный ID задачи
            execute_at: Время выполнения
            action: Асинхронная функция для выполнения
            action_args: Аргументы для функции
            repeat_interval: Интервал повторения (если нужно)
            
        Returns:
            True если задача запланирована
        """
        try:
            task = ScheduledTask(
                task_id=task_id,
                execute_at=execute_at,
                action=action,
                action_args=action_args,
                repeat_interval=repeat_interval
            )
            
            self.tasks[task_id] = task
            self._save_tasks()
            
            logger.info(f"Задача {task_id} запланирована на {execute_at}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при планировании задачи {task_id}: {e}")
            return False
    
    def cancel_task(self, task_id: str) -> bool:
        """Отменяет запланированную задачу."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._save_tasks()
            logger.info(f"Задача {task_id} отменена")
            return True
        return False
    
    def get_scheduled_tasks(self) -> List[Dict[str, Any]]:
        """Возвращает список запланированных задач."""
        return [
            {
                "task_id": task.task_id,
                "execute_at": task.execute_at.isoformat(),
                "repeat_interval": task.repeat_interval.total_seconds() if task.repeat_interval else None,
                "last_executed": task.last_executed.isoformat() if task.last_executed else None
            }
            for task in self.tasks.values()
        ]


# Глобальный экземпляр сервиса
_scheduler_service: Optional[SchedulerService] = None


def get_scheduler_service() -> SchedulerService:
    """Получает глобальный экземпляр SchedulerService."""
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
