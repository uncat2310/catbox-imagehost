"""Authentication and limits are checked before request bodies are parsed."""
import base64
import binascii
import hashlib
import hmac
import time
from urllib.parse import urlsplit

from fastapi import HTTPException
from starlette.responses import JSONResponse

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https://files.catbox.moe blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
}


class PrivateAccess:
    def __init__(self, app, owner):
        self.app, self.owner = app, owner
        self.active_uploads = 0
        self.failures, self.failure_window = 0, time.monotonic()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.decode().lower(): value.decode("latin1") for key, value in scope["headers"]}

        async def secured_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [(key, value) for key, value in message.get("headers", []) if key.lower() not in {k.lower().encode() for k in SECURITY_HEADERS}]
                message["headers"].extend((key.encode(), value.encode()) for key, value in SECURITY_HEADERS.items())
            await send(message)

        async def reject(status, detail, extra=None):
            await JSONResponse({"detail": detail}, status_code=status, headers=extra)(scope, receive, secured_send)

        health = scope["path"] == "/api/health" and scope["method"] == "GET"
        if not health:
            expected = getattr(self.owner.state, "password_digest", None)
            valid = False
            try:
                scheme, token = headers.get("authorization", "").split(" ", 1)
                username, password = base64.b64decode(token, validate=True).decode("utf-8").split(":", 1)
                valid = scheme.lower() == "basic" and username == "admin" and expected is not None and hmac.compare_digest(hashlib.sha256(password.encode()).digest(), expected)
            except (ValueError, UnicodeError, binascii.Error):
                pass
            if not valid:
                now = time.monotonic()
                if now - self.failure_window >= 60:
                    self.failures, self.failure_window = 0, now
                self.failures += 1
                if self.failures > 20:
                    return await reject(429, "登录尝试过多，请稍后重试", {"Retry-After": "60"})
                return await reject(401, "请输入个人图床访问密码", {"WWW-Authenticate": 'Basic realm="Private Catbox", charset="UTF-8"'})
            if scope["method"] not in {"GET", "HEAD", "OPTIONS"} and "origin" in headers:
                try:
                    origin = urlsplit(headers["origin"])
                except ValueError:
                    return await reject(403, "来源无效")
                if origin.scheme not in {"http", "https"} or origin.netloc.lower() != headers.get("host", "").lower():
                    return await reject(403, "不允许跨站修改")

        upload = scope["path"] == "/api/upload" and scope["method"] == "POST"
        if upload and self.active_uploads >= getattr(self.owner.state, "upload_limit", 1):
            return await reject(503, "上传任务已满，请稍后重试", {"Retry-After": "2"})
        limit = self.owner.state.max_size + 1024 * 1024 if upload else 2 * 1024 * 1024
        try:
            length = int(headers.get("content-length", "0"))
            if length < 0:
                raise ValueError
        except ValueError:
            return await reject(400, "请求长度无效")
        if length > limit:
            return await reject(413, "请求体超过大小限制")
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(413, "请求体超过大小限制")
            return message

        if upload:
            self.active_uploads += 1
        try:
            await self.app(scope, limited_receive, secured_send)
        finally:
            if upload:
                self.active_uploads -= 1
