#!/usr/bin/env python3
"""
Database management commands for Digital Twin.
Provides utilities for migrations, backups, and maintenance.
"""
import asyncio
import click
from pathlib import Path
from loguru import logger

from app.core.backup import get_backup_manager


@click.group()
def cli():
    """Digital Twin Database Management Commands."""
    pass


@cli.command()
def init():
    """Initialize Alembic migrations."""
    import subprocess
    result = subprocess.run(["alembic", "revision", "--autogenerate", "-m", "Initial migration"], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        click.echo("✅ Alembic initialized successfully")
        click.echo(result.stdout)
    else:
        click.echo("❌ Failed to initialize Alembic")
        click.echo(result.stderr)


@cli.command()
@click.option("--message", "-m", required=True, help="Migration message")
def migrate(message: str):
    """Create new migration."""
    import subprocess
    result = subprocess.run(["alembic", "revision", "--autogenerate", "-m", message], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        click.echo(f"✅ Migration created: {message}")
        click.echo(result.stdout)
    else:
        click.echo("❌ Failed to create migration")
        click.echo(result.stderr)


@cli.command()
@click.option("--revision", "-r", default="head", help="Target revision (default: head)")
def upgrade(revision: str):
    """Apply migrations."""
    import subprocess
    result = subprocess.run(["alembic", "upgrade", revision], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        click.echo(f"✅ Database upgraded to: {revision}")
        click.echo(result.stdout)
    else:
        click.echo("❌ Failed to upgrade database")
        click.echo(result.stderr)


@cli.command()
@click.option("--revision", "-r", required=True, help="Target revision")
def downgrade(revision: str):
    """Rollback migrations."""
    click.confirm(f"Are you sure you want to downgrade to {revision}?", abort=True)
    
    import subprocess
    result = subprocess.run(["alembic", "downgrade", revision], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        click.echo(f"✅ Database downgraded to: {revision}")
        click.echo(result.stdout)
    else:
        click.echo("❌ Failed to downgrade database")
        click.echo(result.stderr)


@cli.command()
def current():
    """Show current migration revision."""
    import subprocess
    result = subprocess.run(["alembic", "current"], capture_output=True, text=True)
    if result.returncode == 0:
        click.echo("Current revision:")
        click.echo(result.stdout)
    else:
        click.echo("❌ Failed to get current revision")
        click.echo(result.stderr)


@cli.command()
def history():
    """Show migration history."""
    import subprocess
    result = subprocess.run(["alembic", "history"], capture_output=True, text=True)
    if result.returncode == 0:
        click.echo("Migration history:")
        click.echo(result.stdout)
    else:
        click.echo("❌ Failed to get migration history")
        click.echo(result.stderr)


@cli.command()
@click.option("--compress/--no-compress", default=True, help="Compress backup file")
async def backup(compress: bool):
    """Create database backup."""
    try:
        backup_manager = get_backup_manager()
        backup_path = await backup_manager.create_full_backup(compress=compress)
        click.echo(f"✅ Backup created: {backup_path}")
    except Exception as e:
        click.echo(f"❌ Backup failed: {e}")


@cli.command()
@click.option("--tables", help="Comma-separated list of tables to export")
async def export(tables: str):
    """Export data to JSON."""
    try:
        backup_manager = get_backup_manager()
        table_list = tables.split(',') if tables else None
        export_path = await backup_manager.create_data_export(table_list)
        click.echo(f"✅ Data exported: {export_path}")
    except Exception as e:
        click.echo(f"❌ Export failed: {e}")


@cli.command()
@click.argument("backup_path")
async def restore(backup_path: str):
    """Restore database from backup."""
    click.confirm(
        f"This will replace current database with backup from {backup_path}. Continue?", 
        abort=True
    )
    
    try:
        backup_manager = get_backup_manager()
        success = await backup_manager.restore_from_backup(backup_path)
        if success:
            click.echo("✅ Database restored successfully")
        else:
            click.echo("❌ Database restore failed")
    except Exception as e:
        click.echo(f"❌ Restore failed: {e}")


@cli.command()
@click.argument("backup_path")
async def verify_backup(backup_path: str):
    """Verify backup integrity."""
    try:
        backup_manager = get_backup_manager()
        result = await backup_manager.verify_backup(backup_path)
        
        if result["status"] == "ok":
            click.echo("✅ Backup verification passed")
            click.echo(f"File size: {result['file_size']} bytes")
            click.echo(f"Compressed: {result['compressed']}")
            if "metadata" in result:
                click.echo(f"Backup time: {result['metadata'].get('backup_time', 'N/A')}")
        else:
            click.echo("❌ Backup verification failed")
            click.echo(f"Error: {result.get('message', 'Unknown error')}")
    except Exception as e:
        click.echo(f"❌ Verification failed: {e}")


@cli.command()
async def list_backups():
    """List available backups."""
    try:
        backup_manager = get_backup_manager()
        backups = backup_manager.get_backup_list()
        
        if not backups:
            click.echo("No backups found")
            return
        
        click.echo("Available backups:")
        click.echo("-" * 80)
        
        for backup in backups:
            click.echo(f"📁 {backup['filename']}")
            click.echo(f"   Size: {backup['size_bytes']:,} bytes")
            click.echo(f"   Created: {backup['created']}")
            if backup.get('compressed'):
                click.echo("   Compressed: Yes")
            click.echo()
    except Exception as e:
        click.echo(f"❌ Failed to list backups: {e}")


@cli.command()
async def cleanup_backups():
    """Clean up old backups according to retention policy."""
    try:
        backup_manager = get_backup_manager()
        await backup_manager.cleanup_old_backups()
        click.echo("✅ Backup cleanup completed")
    except Exception as e:
        click.echo(f"❌ Cleanup failed: {e}")


@cli.command()
def reset_db():
    """Reset database (WARNING: destroys all data)."""
    click.confirm(
        "This will PERMANENTLY DELETE all data in the database. Are you absolutely sure?", 
        abort=True
    )
    
    # Повторное подтверждение
    click.confirm("Type 'yes' to confirm database reset:", abort=True)
    
    try:
        # Сначала создаем бэкап текущей БД
        async def create_safety_backup():
            backup_manager = get_backup_manager()
            return await backup_manager.create_full_backup()
        
        safety_backup = asyncio.run(create_safety_backup())
        click.echo(f"Safety backup created: {safety_backup}")
        
        # Удаляем все таблицы через Alembic
        import subprocess
        result = subprocess.run(["alembic", "downgrade", "base"], 
                              capture_output=True, text=True)
        if result.returncode != 0:
            click.echo("❌ Failed to reset database")
            click.echo(result.stderr)
            return
        
        # Применяем все миграции заново
        result = subprocess.run(["alembic", "upgrade", "head"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            click.echo("✅ Database reset completed")
        else:
            click.echo("❌ Failed to recreate database")
            click.echo(result.stderr)
            
    except Exception as e:
        click.echo(f"❌ Reset failed: {e}")


# Wrapper для async команд
def async_command(f):
    """Decorator to run async click commands."""
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper


# Применяем декоратор к async командам
backup = async_command(backup)
export = async_command(export)
restore = async_command(restore)
verify_backup = async_command(verify_backup)
list_backups = async_command(list_backups)
cleanup_backups = async_command(cleanup_backups)


if __name__ == "__main__":
    cli()