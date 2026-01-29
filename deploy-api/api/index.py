"""
Точка входа для Vercel при Root Directory = deploy-api.
Папка app — копия apps/api/app (держим в репо, т.к. Build Command при builds в vercel.json не выполняется).
"""
import sys
from pathlib import Path

deploy_api_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(deploy_api_root))

from app.main import app

handler = app
