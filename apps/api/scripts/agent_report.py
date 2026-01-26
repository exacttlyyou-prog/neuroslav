#!/usr/bin/env python3
"""
Скрипт для генерации отчета по использованию агентов.
Анализирует логи и базу данных для сбора статистики.
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any
from collections import Counter, defaultdict
import json

# Добавляем корневую директорию проекта в path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_root))

# Добавляем путь к API для корректных внутренних импортов
api_root = project_root / "apps" / "api"
sys.path.append(str(api_root))

from loguru import logger


class AgentReportService:
    """Сервис для генерации отчетов по использованию агентов."""
    
    def __init__(self):
        self.agent_stats = defaultdict(lambda: {
            "count": 0,
            "total_processing_time_ms": 0,
            "avg_processing_time_ms": 0,
            "confidence_scores": [],
            "avg_confidence": 0.0,
            "chains": Counter(),
            "errors": 0
        })
        self.total_requests = 0
        self.date_range = None
    
    def analyze_logs(self, days_back: int = 7) -> None:
        """
        Анализирует логи за указанный период.
        
        Args:
            days_back: количество дней назад для анализа
        """
        # В реальной системе здесь был бы парсинг логов
        # Пока что создаем фиктивные данные для демонстрации
        logger.info(f"📊 Анализ логов за последние {days_back} дней...")
        
        # Фиктивные данные для демонстрации
        fake_data = [
            {"agent_type": "task", "processing_time_ms": 1250, "confidence": 0.95, "chains": ["knowledge"], "error": False},
            {"agent_type": "task", "processing_time_ms": 890, "confidence": 0.88, "chains": [], "error": False},
            {"agent_type": "meeting", "processing_time_ms": 3400, "confidence": 0.92, "chains": ["task"], "error": False},
            {"agent_type": "meeting", "processing_time_ms": 2100, "confidence": 0.89, "chains": ["task", "knowledge"], "error": False},
            {"agent_type": "knowledge", "processing_time_ms": 670, "confidence": 0.91, "chains": [], "error": False},
            {"agent_type": "rag_query", "processing_time_ms": 1100, "confidence": 0.85, "chains": [], "error": False},
            {"agent_type": "rag_query", "processing_time_ms": 950, "confidence": 0.78, "chains": [], "error": False},
            {"agent_type": "default", "processing_time_ms": 450, "confidence": 0.65, "chains": [], "error": False},
            {"agent_type": "message", "processing_time_ms": 780, "confidence": 0.90, "chains": [], "error": False},
            {"agent_type": "task", "processing_time_ms": 0, "confidence": 0.88, "chains": [], "error": True},
        ]
        
        self.total_requests = len(fake_data)
        self.date_range = (
            datetime.now() - timedelta(days=days_back),
            datetime.now()
        )
        
        # Обрабатываем данные
        for entry in fake_data:
            agent_type = entry["agent_type"]
            stats = self.agent_stats[agent_type]
            
            stats["count"] += 1
            
            if not entry["error"]:
                stats["total_processing_time_ms"] += entry["processing_time_ms"]
                stats["confidence_scores"].append(entry["confidence"])
                
                # Записываем цепочки
                if entry["chains"]:
                    chain_str = f"{agent_type} -> {' -> '.join(entry['chains'])}"
                    stats["chains"][chain_str] += 1
            else:
                stats["errors"] += 1
        
        # Вычисляем средние значения
        for agent_type, stats in self.agent_stats.items():
            if stats["count"] > stats["errors"]:
                successful_count = stats["count"] - stats["errors"]
                stats["avg_processing_time_ms"] = stats["total_processing_time_ms"] // successful_count
                if stats["confidence_scores"]:
                    stats["avg_confidence"] = sum(stats["confidence_scores"]) / len(stats["confidence_scores"])
    
    async def analyze_database(self) -> Dict[str, Any]:
        """
        Анализирует данные из базы данных.
        
        Returns:
            Статистика из базы данных
        """
        try:
            # Загружаем переменные окружения
            from dotenv import load_dotenv
            load_dotenv(project_root / ".env")
            
            # Исправляем путь к БД
            import os
            database_url = os.getenv("DATABASE_URL", "sqlite:///./data/digital_twin.db")
            if "sqlite:///" in database_url and not database_url.startswith("sqlite:////"):
                relative_path = database_url.split("sqlite:///")[1]
                if relative_path.startswith("./"):
                    relative_path = relative_path[2:]
                db_path = api_root / relative_path
                os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
            
            from apps.api.app.db.database import AsyncSessionLocal
            from apps.api.app.db.models import Task, Meeting
            from sqlalchemy import text, func
            
            db_stats = {
                "tasks_total": 0,
                "tasks_completed": 0,
                "tasks_pending": 0,
                "meetings_total": 0,
                "meetings_processed": 0,
                "recent_activity": []
            }
            
            async with AsyncSessionLocal() as db:
                # Статистика задач
                result = await db.execute(text("SELECT COUNT(*) FROM tasks"))
                db_stats["tasks_total"] = result.scalar() or 0
                
                result = await db.execute(text("SELECT COUNT(*) FROM tasks WHERE status = 'completed'"))
                db_stats["tasks_completed"] = result.scalar() or 0
                
                result = await db.execute(text("SELECT COUNT(*) FROM tasks WHERE status != 'completed'"))
                db_stats["tasks_pending"] = result.scalar() or 0
                
                # Статистика встреч
                result = await db.execute(text("SELECT COUNT(*) FROM meetings"))
                db_stats["meetings_total"] = result.scalar() or 0
                
                result = await db.execute(text("SELECT COUNT(*) FROM meetings WHERE status = 'processed'"))
                db_stats["meetings_processed"] = result.scalar() or 0
                
                # Последние 5 задач
                result = await db.execute(text("""
                    SELECT title, created_at, status 
                    FROM tasks 
                    ORDER BY created_at DESC 
                    LIMIT 5
                """))
                
                for row in result.fetchall():
                    db_stats["recent_activity"].append({
                        "type": "task",
                        "title": row[0] or "Без названия",
                        "created_at": row[1],
                        "status": row[2]
                    })
                
            return db_stats
            
        except Exception as e:
            logger.warning(f"Ошибка при анализе БД: {e}")
            return {
                "tasks_total": 0,
                "tasks_completed": 0,
                "tasks_pending": 0,
                "meetings_total": 0,
                "meetings_processed": 0,
                "recent_activity": [],
                "error": str(e)
            }
    
    def generate_report(self, db_stats: Dict[str, Any] = None) -> str:
        """
        Генерирует текстовый отчет.
        
        Args:
            db_stats: статистика из базы данных
            
        Returns:
            Форматированный отчет
        """
        # Эмодзи для агентов
        agent_emojis = {
            "task": "📋",
            "meeting": "🎯",
            "message": "📨", 
            "knowledge": "🧠",
            "rag_query": "🔍",
            "default": "🤖"
        }
        
        report_lines = []
        report_lines.append("📊 <b>ОТЧЕТ ПО СИСТЕМЕ АГЕНТОВ</b>\n")
        
        if self.date_range:
            start_date = self.date_range[0].strftime("%d.%m.%Y")
            end_date = self.date_range[1].strftime("%d.%m.%Y")
            report_lines.append(f"📅 <b>Период:</b> {start_date} - {end_date}")
        
        report_lines.append(f"📈 <b>Всего запросов:</b> {self.total_requests}")
        report_lines.append("")
        
        # Статистика по агентам
        report_lines.append("🤖 <b>СТАТИСТИКА АГЕНТОВ</b>")
        
        # Сортируем агентов по популярности
        sorted_agents = sorted(
            self.agent_stats.items(), 
            key=lambda x: x[1]["count"], 
            reverse=True
        )
        
        for agent_type, stats in sorted_agents:
            emoji = agent_emojis.get(agent_type, "🤖")
            success_rate = ((stats["count"] - stats["errors"]) / stats["count"] * 100) if stats["count"] > 0 else 0
            
            report_lines.append(
                f"{emoji} <b>{agent_type.title()}Agent:</b> {stats['count']} запросов"
            )
            
            if stats["avg_processing_time_ms"] > 0:
                report_lines.append(
                    f"   ⏱ Среднее время: {stats['avg_processing_time_ms']}мс"
                )
            
            if stats["avg_confidence"] > 0:
                report_lines.append(
                    f"   🎯 Средняя уверенность: {stats['avg_confidence']:.0%}"
                )
            
            if stats["errors"] > 0:
                report_lines.append(f"   ❌ Ошибок: {stats['errors']}")
            
            report_lines.append(f"   ✅ Успешность: {success_rate:.0%}")
            report_lines.append("")
        
        # Популярные цепочки агентов
        all_chains = Counter()
        for stats in self.agent_stats.values():
            all_chains.update(stats["chains"])
        
        if all_chains:
            report_lines.append("🔗 <b>ПОПУЛЯРНЫЕ ЦЕПОЧКИ АГЕНТОВ</b>")
            for chain, count in all_chains.most_common(3):
                report_lines.append(f"• {chain} ({count}x)")
            report_lines.append("")
        
        # Статистика базы данных
        if db_stats:
            report_lines.append("💾 <b>ДАННЫЕ В СИСТЕМЕ</b>")
            report_lines.append(f"📋 Задач всего: {db_stats['tasks_total']}")
            report_lines.append(f"   ✅ Завершено: {db_stats['tasks_completed']}")
            report_lines.append(f"   ⏳ В работе: {db_stats['tasks_pending']}")
            report_lines.append("")
            report_lines.append(f"🎯 Встреч всего: {db_stats['meetings_total']}")
            report_lines.append(f"   ✅ Обработано: {db_stats['meetings_processed']}")
            
            if db_stats.get("error"):
                report_lines.append(f"\n⚠️ Ошибка БД: {db_stats['error']}")
        
        return "\n".join(report_lines)
    
    async def generate_full_report(self, days_back: int = 7) -> str:
        """
        Генерирует полный отчет с анализом логов и БД.
        
        Args:
            days_back: количество дней для анализа
            
        Returns:
            Полный отчет
        """
        logger.info("📊 Генерация отчета по агентам...")
        
        # Анализируем логи
        self.analyze_logs(days_back)
        
        # Анализируем БД
        db_stats = await self.analyze_database()
        
        # Генерируем отчет
        report = self.generate_report(db_stats)
        
        logger.info("✅ Отчет сгенерирован")
        return report


async def main():
    """Основная функция для запуска из командной строки."""
    report_service = AgentReportService()
    
    # Параметры по умолчанию
    days_back = 7
    
    # Если переданы аргументы командной строки
    if len(sys.argv) > 1:
        try:
            days_back = int(sys.argv[1])
        except ValueError:
            logger.error("Неверный аргумент. Использование: python agent_report.py [дни]")
            return
    
    # Генерируем отчет
    try:
        report = await report_service.generate_full_report(days_back)
        print("\n" + report)
        
    except Exception as e:
        logger.error(f"Ошибка при генерации отчета: {e}")


if __name__ == "__main__":
    asyncio.run(main())