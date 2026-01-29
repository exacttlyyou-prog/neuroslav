"""
Точка входа для Vercel при Root Directory = deploy-api.
Папка app создаётся при сборке (Build Command: bash copy-app.sh).
"""
import sys
from pathlib import Path

deploy_api_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(deploy_api_root))

from app.main import app

handler = app
