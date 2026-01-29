"""
Точка входа Vercel при Root = корень репо. Ленивая загрузка app из apps/api + traceback при ошибке.
"""
import sys
import traceback
from pathlib import Path

# Путь к apps/api (источник приложения при корневом деплое)
apps_api = Path(__file__).resolve().parent.parent / "apps" / "api"
sys.path.insert(0, str(apps_api))

_app = None


async def _send(send, status: int, body: bytes):
    await send({"type": "http.response.start", "status": status, "headers": [[b"content-type", b"text/plain; charset=utf-8"]]})
    await send({"type": "http.response.body", "body": body})


async def _serve(scope, receive, send):
    if scope.get("type") != "http":
        return
    global _app
    if _app is None:
        try:
            from app.main import app
            _app = app
        except Exception as e:
            tb = traceback.format_exc()
            await _send(send, 500, f"Import error:\n{e!r}\n\n{tb}".encode("utf-8"))
            return
    try:
        await _app(scope, receive, send)
    except Exception as e:
        tb = traceback.format_exc()
        await _send(send, 500, f"Runtime error:\n{e!r}\n\n{tb}".encode("utf-8"))


handler = _serve
