"""
Точка входа для Vercel при Root Directory = deploy-api.
Без импорта app при загрузке — иначе Vercel ловит падение и отдаёт generic 500.
По / — 200 OK. По /load-full-app — попытка импорта и ответ с traceback или ok.
"""
import sys
import traceback
from pathlib import Path

deploy_api_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(deploy_api_root))

# Полное приложение грузим по требованию (при первом запросе или по /load-full-app)
_app = None


async def _send(send, status: int, body: bytes, content_type: str = "text/plain; charset=utf-8"):
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [[b"content-type", content_type.encode("utf-8")]],
    })
    await send({"type": "http.response.body", "body": body})


async def _minimal_app(scope, receive, send):
    if scope["type"] != "http":
        return
    path = (scope.get("path") or "").strip()
    # Отладочный маршрут: загрузить полное приложение и вернуть результат
    if path == "/load-full-app":
        try:
            from app.main import app as full_app
            global _app
            _app = full_app
            await _send(send, 200, b"ok: app loaded")
        except Exception as e:
            tb = traceback.format_exc()
            msg = f"Import error: {e!r}\n\nTraceback:\n{tb}"
            await _send(send, 500, msg.encode("utf-8"))
        return
    # Все остальные запросы: если приложение уже загружено — прокидываем, иначе пробуем загрузить один раз
    if _app is not None:
        try:
            await _app(scope, receive, send)
        except Exception as e:
            tb = traceback.format_exc()
            await _send(send, 500, f"Runtime: {e!r}\n\n{tb}".encode("utf-8"))
        return
    try:
        from app.main import app as full_app
        global _app
        _app = full_app
        await _app(scope, receive, send)
    except Exception as e:
        tb = traceback.format_exc()
        await _send(send, 500, f"Import/Runtime: {e!r}\n\n{tb}".encode("utf-8"))


handler = _minimal_app
