# Минимальный handler: без импортов, без sys.path.
# Если этот ответ видишь — проект и Root Directory настроены верно.
# Потом вернём полное приложение.

async def handler(scope, receive, send):
    if scope.get("type") == "http":
        await send({"type": "http.response.start", "status": 200, "headers": [[b"content-type", b"text/plain; charset=utf-8"]]})
        await send({"type": "http.response.body", "body": b"deploy-api ok"})
