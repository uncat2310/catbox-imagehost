"""Catbox.moe API 客户端"""

import asyncio
from typing import BinaryIO, Optional
import aiohttp

API = "https://catbox.moe/user/api.php"
TIMEOUT = aiohttp.ClientTimeout(total=120)


class CatboxError(Exception):
    pass


async def upload_file(
    content: bytes | BinaryIO,
    filename: str,
    userhash: Optional[str] = None,
    session: aiohttp.ClientSession | None = None,
) -> str:
    """上传文件，返回直链 URL"""
    data = aiohttp.FormData()
    data.add_field("reqtype", "fileupload")
    data.add_field("fileToUpload", content, filename=filename)
    if userhash:
        data.add_field("userhash", userhash)

    if session:
        text = await _post_form(session, data)
    else:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as owned_session:
            text = await _post_form(owned_session, data)

    from backend.models import safe_url
    try:
        return safe_url(text)
    except ValueError:
        raise CatboxError("Catbox 返回了无效文件地址") from None


async def _post_form(session: aiohttp.ClientSession, data: aiohttp.FormData) -> str:
    async with session.post(API, data=data, allow_redirects=False) as resp:
        try:
            raw = await resp.content.readexactly(4097)
        except asyncio.IncompleteReadError as exc:
            raw = exc.partial
        if len(raw) > 4096:
            raise CatboxError("Catbox 响应过大")
        text = raw.decode("utf-8", errors="replace").strip()
        if resp.status >= 400:
            raise CatboxError(f"Catbox HTTP {resp.status}")
        return text


async def delete_files(urls: list[str], userhash: str) -> str:
    """删除文件，需要 userhash"""
    data = aiohttp.FormData()
    data.add_field("reqtype", "deletefiles")
    data.add_field("files", " ".join(urls))
    data.add_field("userhash", userhash)

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        text = await _post_form(session, data)
        return text
