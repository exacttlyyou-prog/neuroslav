"""
Система резервного копирования базы данных Digital Twin.
"""
import os
import shutil
import gzip
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import AsyncSessionLocal


class DatabaseBackupManager:
    """Менеджер резервного копирования базы данных."""
    
    def __init__(self, backup_dir: str = "backups"):
        self.settings = get_settings()
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        
        # Настройки ротации
        self.keep_daily_backups = 7     # 7 дней ежедневных
        self.keep_weekly_backups = 4    # 4 недели еженедельных  
        self.keep_monthly_backups = 6   # 6 месяцев ежемесячных
    
    async def create_full_backup(self, compress: bool = True) -> str:
        """Создает полный бэкап базы данных."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"digital_twin_backup_{timestamp}.sql"
        
        if compress:
            backup_filename += ".gz"
        
        backup_path = self.backup_dir / backup_filename
        
        try:
            if self._is_sqlite():
                await self._backup_sqlite(backup_path, compress)
            else:
                await self._backup_postgresql(backup_path, compress)
            
            logger.info(f"Database backup created: {backup_path}")
            
            # Добавляем метаданные
            await self._create_backup_metadata(backup_path, "full")
            
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            if backup_path.exists():
                backup_path.unlink()  # Удаляем частичный бэкап
            raise
    
    async def create_data_export(self, tables: List[str] = None) -> str:
        """Создает экспорт данных в JSON формате."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"digital_twin_export_{timestamp}.json.gz"
        export_path = self.backup_dir / export_filename
        
        try:
            async with AsyncSessionLocal() as session:
                data = {}
                
                # Определяем таблицы для экспорта
                export_tables = tables or ["meetings"]  # Добавьте другие таблицы по необходимости
                
                for table_name in export_tables:
                    logger.info(f"Exporting table: {table_name}")
                    
                    # Выполняем запрос для получения данных
                    result = await session.execute(text(f"SELECT * FROM {table_name}"))
                    rows = result.fetchall()
                    columns = result.keys()
                    
                    # Преобразуем в список словарей
                    table_data = []
                    for row in rows:
                        row_dict = {}
                        for i, column in enumerate(columns):
                            value = row[i]
                            # Сериализуем datetime объекты
                            if isinstance(value, datetime):
                                value = value.isoformat()
                            row_dict[column] = value
                        table_data.append(row_dict)
                    
                    data[table_name] = table_data
                
                # Добавляем метаданные
                data["_metadata"] = {
                    "export_time": datetime.now().isoformat(),
                    "tables": export_tables,
                    "total_records": sum(len(table_data) for table_data in data.values() if isinstance(table_data, list))
                }
                
                # Записываем сжатый JSON
                json_str = json.dumps(data, ensure_ascii=False, indent=2)
                with gzip.open(export_path, 'wt', encoding='utf-8') as f:
                    f.write(json_str)
                
                logger.info(f"Data export created: {export_path}")
                return str(export_path)
                
        except Exception as e:
            logger.error(f"Failed to create data export: {e}")
            if export_path.exists():
                export_path.unlink()
            raise
    
    async def restore_from_backup(self, backup_path: str) -> bool:
        """Восстанавливает базу данных из бэкапа."""
        backup_file = Path(backup_path)
        
        if not backup_file.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")
        
        try:
            logger.info(f"Starting database restore from: {backup_path}")
            
            # Создаем бэкап текущей БД перед восстановлением
            current_backup = await self.create_full_backup()
            logger.info(f"Current database backed up to: {current_backup}")
            
            if self._is_sqlite():
                success = await self._restore_sqlite(backup_file)
            else:
                success = await self._restore_postgresql(backup_file)
            
            if success:
                logger.info("Database restore completed successfully")
            else:
                logger.error("Database restore failed")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to restore database: {e}")
            return False
    
    async def cleanup_old_backups(self):
        """Очищает старые бэкапы согласно политике ротации."""
        try:
            backups = list(self.backup_dir.glob("digital_twin_backup_*.sql*"))
            backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            
            now = datetime.now()
            kept_backups = []
            removed_count = 0
            
            for backup_file in backups:
                backup_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
                age = now - backup_time
                
                should_keep = False
                
                # Ежедневные бэкапы (последние 7 дней)
                if age.days < self.keep_daily_backups:
                    should_keep = True
                    
                # Еженедельные бэкапы (последние 4 недели)
                elif age.days < self.keep_weekly_backups * 7 and backup_time.weekday() == 0:  # Понедельник
                    should_keep = True
                    
                # Ежемесячные бэкапы (последние 6 месяцев)
                elif age.days < self.keep_monthly_backups * 30 and backup_time.day == 1:  # Первое число месяца
                    should_keep = True
                
                if should_keep:
                    kept_backups.append(backup_file)
                else:
                    # Удаляем старый бэкап и его метаданные
                    backup_file.unlink()
                    metadata_file = backup_file.with_suffix('.metadata.json')
                    if metadata_file.exists():
                        metadata_file.unlink()
                    removed_count += 1
            
            logger.info(f"Backup cleanup: kept {len(kept_backups)}, removed {removed_count}")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {e}")
    
    def _is_sqlite(self) -> bool:
        """Проверяет использует ли приложение SQLite."""
        return "sqlite" in self.settings.database_url.lower()
    
    async def _backup_sqlite(self, backup_path: Path, compress: bool):
        """Создает бэкап SQLite базы данных."""
        # Получаем путь к файлу базы данных
        db_url = self.settings.database_url
        if db_url.startswith("sqlite:///"):
            db_file = db_url[10:]  # Убираем sqlite:///
        else:
            raise ValueError("Invalid SQLite URL format")
        
        source_path = Path(db_file)
        if not source_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_file}")
        
        if compress:
            # Сжимаем файл при копировании
            with open(source_path, 'rb') as f_in:
                with gzip.open(backup_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            # Простое копирование
            shutil.copy2(source_path, backup_path)
    
    async def _backup_postgresql(self, backup_path: Path, compress: bool):
        """Создает бэкап PostgreSQL базы данных."""
        # Здесь должна быть логика для PostgreSQL pg_dump
        # Для простоты пока не реализуем
        raise NotImplementedError("PostgreSQL backup not implemented yet")
    
    async def _restore_sqlite(self, backup_file: Path) -> bool:
        """Восстанавливает SQLite базу данных."""
        try:
            db_url = self.settings.database_url
            if db_url.startswith("sqlite:///"):
                db_file = Path(db_url[10:])
            else:
                raise ValueError("Invalid SQLite URL format")
            
            if backup_file.suffix == '.gz':
                # Распаковываем сжатый файл
                with gzip.open(backup_file, 'rb') as f_in:
                    with open(db_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
            else:
                # Простое копирование
                shutil.copy2(backup_file, db_file)
            
            return True
            
        except Exception as e:
            logger.error(f"SQLite restore failed: {e}")
            return False
    
    async def _restore_postgresql(self, backup_file: Path) -> bool:
        """Восстанавливает PostgreSQL базу данных."""
        # Здесь должна быть логика для PostgreSQL pg_restore
        raise NotImplementedError("PostgreSQL restore not implemented yet")
    
    async def _create_backup_metadata(self, backup_path: Path, backup_type: str):
        """Создает файл метаданных для бэкапа."""
        metadata = {
            "backup_time": datetime.now().isoformat(),
            "backup_type": backup_type,
            "database_url_type": "sqlite" if self._is_sqlite() else "postgresql",
            "file_size_bytes": backup_path.stat().st_size,
            "compressed": backup_path.suffix == '.gz'
        }
        
        metadata_path = backup_path.with_suffix('.metadata.json')
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    def get_backup_list(self) -> List[Dict[str, Any]]:
        """Возвращает список доступных бэкапов."""
        backups = []
        
        for backup_file in self.backup_dir.glob("digital_twin_backup_*.sql*"):
            metadata_file = backup_file.with_suffix('.metadata.json')
            
            backup_info = {
                "filename": backup_file.name,
                "path": str(backup_file),
                "size_bytes": backup_file.stat().st_size,
                "created": datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat()
            }
            
            # Добавляем метаданные если доступны
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    backup_info.update(metadata)
                except Exception as e:
                    logger.warning(f"Failed to read backup metadata: {e}")
            
            backups.append(backup_info)
        
        # Сортируем по времени создания (новые первые)
        backups.sort(key=lambda x: x['created'], reverse=True)
        return backups
    
    async def verify_backup(self, backup_path: str) -> Dict[str, Any]:
        """Проверяет целостность бэкапа."""
        backup_file = Path(backup_path)
        
        if not backup_file.exists():
            return {"status": "error", "message": "Backup file not found"}
        
        try:
            result = {
                "status": "ok",
                "file_exists": True,
                "file_size": backup_file.stat().st_size,
                "readable": True,
                "compressed": backup_file.suffix == '.gz'
            }
            
            # Проверяем возможность чтения файла
            if result["compressed"]:
                with gzip.open(backup_file, 'rb') as f:
                    f.read(1024)  # Читаем первые 1KB
            else:
                with open(backup_file, 'rb') as f:
                    f.read(1024)
            
            # Проверяем метаданные
            metadata_file = backup_file.with_suffix('.metadata.json')
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    result["metadata"] = json.load(f)
            
            return result
            
        except Exception as e:
            return {
                "status": "error", 
                "message": f"Backup verification failed: {str(e)}"
            }


class BackupScheduler:
    """Планировщик автоматических бэкапов."""
    
    def __init__(self, backup_manager: DatabaseBackupManager):
        self.backup_manager = backup_manager
        self.running = False
    
    async def start_scheduled_backups(self):
        """Запускает автоматические бэкапы."""
        self.running = True
        logger.info("Starting scheduled backup service")
        
        while self.running:
            try:
                # Проверяем нужно ли создать бэкап
                if await self._should_create_backup():
                    await self.backup_manager.create_full_backup()
                    logger.info("Scheduled backup completed")
                
                # Очищаем старые бэкапы
                await self.backup_manager.cleanup_old_backups()
                
                # Ждем час до следующей проверки
                await asyncio.sleep(3600)
                
            except Exception as e:
                logger.error(f"Error in backup scheduler: {e}")
                await asyncio.sleep(300)  # При ошибке ждем 5 минут
    
    async def _should_create_backup(self) -> bool:
        """Определяет нужно ли создавать бэкап."""
        # Проверяем есть ли бэкап за последние 24 часа
        backups = self.backup_manager.get_backup_list()
        
        if not backups:
            return True  # Нет бэкапов - создаем
        
        # Проверяем время последнего бэкапа
        last_backup_time = datetime.fromisoformat(backups[0]['created'])
        time_since_backup = datetime.now() - last_backup_time
        
        # Создаем бэкап если прошло больше 24 часов
        return time_since_backup.total_seconds() > 86400
    
    def stop(self):
        """Останавливает планировщик."""
        self.running = False


# Глобальные экземпляры
_backup_manager: Optional[DatabaseBackupManager] = None
_backup_scheduler: Optional[BackupScheduler] = None


def get_backup_manager() -> DatabaseBackupManager:
    """Получает глобальный экземпляр менеджера бэкапов."""
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = DatabaseBackupManager()
    return _backup_manager


def get_backup_scheduler() -> BackupScheduler:
    """Получает глобальный экземпляр планировщика бэкапов."""
    global _backup_scheduler
    if _backup_scheduler is None:
        _backup_scheduler = BackupScheduler(get_backup_manager())
    return _backup_scheduler