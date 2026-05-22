"""Catbox 图床 —— FastAPI 后端"""

import asyncio
import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.config import (
    merge_settings, get_settings,
    get_history, add_history, remove_history_batch,
    export_data, import_data,
)
from backend.catbox_client import upload_file, CatboxError
from backend.image_processor import process_image, is_image

# ── 应用配置 ──────────────────────────────────────────────

APP_VERSION = "3.2.0"

app = FastAPI(title="Catbox 图床", version=APP_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
MAX_SIZE = 200 * 1024 * 1024
MAX_FILES = 20
MAX_CONCURRENT_UPLOADS = 6

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── 工具 ──────────────────────────────────────────────────

def _guess_type(filename: str | None) -> str:
    """根据 MIME 判断文件分类"""
    ct, _ = mimetypes.guess_type(filename or "")
    if not ct:
        return "unknown"
    for prefix, kind in [("image/", "image"), ("video/", "video"), ("audio/", "audio"), ("text/", "text")]:
        if ct.startswith(prefix):
            return kind
    return "unknown"


def _replace_extension(filename: str, ext: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return f"{stem}.{ext}"


async def _upload_one(
    file: UploadFile,
    settings: dict,
    userhash: str,
    semaphore: asyncio.Semaphore,
    session: aiohttp.ClientSession,
) -> tuple[dict | None, dict | None]:
    """读取、可选处理并上传单个文件。"""
    async with semaphore:
        try:
            content = await file.read()
            if len(content) > MAX_SIZE:
                return None, {"filename": file.filename, "error": "文件超过 200MB 限制"}

            filename = file.filename or "untitled"
            body = content
            processed = False

            if await asyncio.to_thread(is_image, content):
                try:
                    body, ext = await asyncio.to_thread(
                        process_image,
                        content,
                        settings["webp_enabled"],
                        settings["webp_quality"],
                    )
                    processed = True
                    if settings["webp_enabled"]:
                        filename = _replace_extension(filename, ext)
                except Exception:
                    pass

            url = await upload_file(body, filename, userhash, session=session)
            return {
                "filename": filename,
                "url": url,
                "size": len(body),
                "type": _guess_type(filename),
                "time": datetime.now(timezone.utc).isoformat(),
                "processed": processed,
            }, None

        except CatboxError as e:
            return None, {"filename": file.filename, "error": str(e)}
        except Exception as e:
            return None, {"filename": file.filename, "error": f"上传异常: {e}"}


# ── 页面 ──────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "version": APP_VERSION}


# ── 配置 ──────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    return get_settings()


@app.post("/api/config")
async def save_config(data: dict):
    merge_settings(data)
    return {"ok": True}


# ── 上传 ──────────────────────────────────────────────────

@app.post("/api/upload")
async def upload(
    files: list[UploadFile] = File(...),
    userhash: Optional[str] = Form(None),
):
    """批量上传到 Catbox.moe"""
    if not userhash:
        raise HTTPException(400, "请先在设置中填入 Userhash")

    if len(files) > MAX_FILES:
        raise HTTPException(400, f"单次最多 {MAX_FILES} 个文件")

    settings = get_settings()
    concurrency = min(settings["upload_concurrency"], MAX_CONCURRENT_UPLOADS, len(files))
    semaphore = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
        uploaded = await asyncio.gather(*(
            _upload_one(file, settings, userhash, semaphore, session)
            for file in files
        ))

    results = [result for result, _ in uploaded if result]
    errors = [error for _, error in uploaded if error]

    for entry in results:
        add_history(entry)

    return {"ok": True, "results": results, "errors": errors, "total": len(files), "concurrency": concurrency}


# ── 历史 ──────────────────────────────────────────────────

@app.get("/api/history")
async def history_list():
    return {"history": get_history()}


@app.post("/api/history/delete")
async def history_delete(data: dict):
    urls = data.get("urls", [])
    if not urls:
        raise HTTPException(400, "请提供要删除的 URL")
    return {"ok": True, "deleted": remove_history_batch(urls)}


# ── 导出 / 导入 ──────────────────────────────────────────

@app.get("/api/export")
async def export():
    data = export_data()
    return Response(
        content=json.dumps(data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=catbox_backup.json"},
    )


@app.post("/api/import")
async def import_backup(data: dict):
    try:
        return import_data(data)
    except Exception as e:
        raise HTTPException(400, f"导入失败: {e}")
