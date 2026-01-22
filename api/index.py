"""
Vercel serverless function adapter для FastAPI.
"""
import sys
from pathlib import Path

# Добавляем путь к приложению
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps" / "api"))

from app.main import app

# Vercel ожидает handler функцию
handler = app
