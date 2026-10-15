"""Single-owner Catbox dashboard. Credentials belong to the deployment."""
import asyncio
import hashlib
import json
import mimetypes
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile

from backend import config
from backend.catbox_client import upload_file, CatboxError
from backend.image_processor import is_image, process_image, ImageLimitError
from backend.models import Backup, HistoryDelete, SettingsPatch
from backend.security import PrivateAccess

APP_VERSION = "4.0.0"
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
MAX_IMAGE_INPUT = 20 * 1024 * 1024


@asynccontextmanager
async def lifespan(app):
    userhash = os.environ.get("CATBOX_USERHASH", "").strip()
    password = os.environ.get("APP_PASSWORD", "")
    if not userhash or userhash == "replace-me":
        raise RuntimeError("请在部署环境配置 CATBOX_USERHASH")
    if len(password) < 8 or password == "replace-with-a-long-random-password":
        raise RuntimeError("APP_PASSWORD 必须至少 8 位，推荐使用独立的随机访问密码")
    app.state.userhash = userhash
    app.state.image_slots = asyncio.Semaphore(1)
    app.state.password_digest = hashlib.sha256(password.encode()).digest()
    await asyncio.to_thread(config.initialize)
    app.state.upload_limit = (await asyncio.to_thread(config.get_settings))["upload_concurrency"]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120), connector=aiohttp.TCPConnector(limit=6)) as session:
        app.state.session = session
        yield


app = FastAPI(title="个人 Catbox 图床", version=APP_VERSION, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.state.max_size = max(1, min(200, int(os.environ.get("MAX_FILE_SIZE_MB", "200")))) * 1024 * 1024
app.add_middleware(PrivateAccess, owner=app)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(FRONTEND_DIR / "favicon.ico")


@app.get("/api/health")
async def health():
    return {"ok": True, "version": APP_VERSION}


@app.get("/api/config")
async def get_config():
    return {**await asyncio.to_thread(config.get_settings), "max_file_size_mb": app.state.max_size // (1024 * 1024)}


@app.post("/api/config")
async def save_config(data: SettingsPatch):
    await asyncio.to_thread(config.merge_settings, data.model_dump(exclude_none=True))
    app.state.upload_limit = (await asyncio.to_thread(config.get_settings))["upload_concurrency"]
    return {"ok": True}


def _guess_type(filename):
    content_type = mimetypes.guess_type(filename)[0] or ""
    kind = content_type.split("/")[0]
    return kind if kind in {"image", "audio", "video", "text"} else "unknown"


async def _upload_one(file, settings):
    filename = (file.filename or "untitled").replace("\\", "/").rsplit("/", 1)[-1][:240] or "untitled"
    try:
        if file.size is None or file.size > app.state.max_size:
            return None, {"filename": filename, "error": "文件超过大小限制"}
        await file.seek(0)
        body, size, processed, warning = file.file, file.size, False, None
        static_image = await asyncio.to_thread(is_image, file.file)
        if static_image and file.size <= MAX_IMAGE_INPUT:
            content = await file.read(MAX_IMAGE_INPUT + 1)
            try:
                async with app.state.image_slots:
                    converted, ext = await asyncio.to_thread(process_image, content, settings["webp_enabled"], settings["webp_quality"])
                if settings["webp_enabled"] or len(converted) < len(content):
                    body, size = converted, len(converted)
                    filename = f"{Path(filename).stem}.{ext}"
                    processed = True
            except ImageLimitError:
                raise
            except Exception:
                warning = "图片处理失败，已使用原文件上传"
        elif static_image:
            warning = "图片超过转码大小限制，已使用原文件上传"
        if size > app.state.max_size:
            return None, {"filename": filename, "error": "处理后的文件超过大小限制"}
        await file.seek(0)
        url = await upload_file(body, filename, app.state.userhash, session=app.state.session)
        entry = {"filename": filename, "url": url, "size": size, "type": _guess_type(filename),
                 "time": datetime.now(timezone.utc).isoformat(), "processed": processed}
        if warning:
            entry["warning"] = warning
        return entry, None
    except ImageLimitError as exc:
        return None, {"filename": filename, "error": str(exc)}
    except (CatboxError, aiohttp.ClientError, asyncio.TimeoutError):
        return None, {"filename": filename, "error": "Catbox 上传失败或超时，请稍后重试"}
    except Exception:
        return None, {"filename": filename, "error": "文件处理失败，请检查文件后重试"}


@app.post("/api/upload")
async def upload(request: Request):
    # Admission and byte counting run in middleware before multipart parsing.
    async with request.form(max_files=20, max_fields=0, max_part_size=1024) as form:
        files = [value for key, value in form.multi_items() if key == "files" and isinstance(value, UploadFile)]
        if not files or len(files) != len(form.multi_items()):
            raise HTTPException(400, "请仅提交 files 文件字段")
        if sum(file.size or 0 for file in files) > app.state.max_size:
            raise HTTPException(413, "单次上传文件总大小超过限制")
        settings = await asyncio.to_thread(config.get_settings)
        # Across requests the middleware caps total uploads; batches stream sequentially.
        uploaded = [await _upload_one(file, settings) for file in files]
        results = [entry for entry, _ in uploaded if entry]
        errors = [error for _, error in uploaded if error]
        if results:
            await asyncio.to_thread(config.add_history_batch, results)
        return {"ok": True, "results": results, "errors": errors, "total": len(files)}


@app.get("/api/history")
async def history():
    return {"history": await asyncio.to_thread(config.get_history)}


@app.post("/api/history/delete")
async def delete_history(data: HistoryDelete):
    return {"ok": True, "deleted": await asyncio.to_thread(config.remove_history_batch, data.urls)}


@app.get("/api/export")
async def export():
    data = await asyncio.to_thread(config.export_data)
    return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=catbox_backup.json"})


@app.post("/api/import")
async def import_backup(data: Backup):
    result = await asyncio.to_thread(config.import_data, data.model_dump())
    app.state.upload_limit = (await asyncio.to_thread(config.get_settings))["upload_concurrency"]
    return result
