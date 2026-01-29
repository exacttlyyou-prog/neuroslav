"""
Точка входа для Vercel при Root Directory = deploy-api.
Папка deploy-api/app — симлинк на ../apps/api/app, чтобы бандл включал код API.
"""
import sys
from pathlib import Path

# deploy-api в path (здесь лежит app -> ../apps/api/app)
deploy_api_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(deploy_api_root))

from app.main import app

handler = app
