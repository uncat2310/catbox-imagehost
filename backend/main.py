"""Catbox 图床 —— FastAPI 后端"""

import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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

APP_VERSION = "3.1.0"

app = FastAPI(title="Catbox 图床", version=APP_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
MAX_SIZE = 200 * 1024 * 1024
MAX_FILES = 20

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
    results, errors = [], []

    for file in files:
        try:
            content = await file.read()
            if len(content) > MAX_SIZE:
                errors.append({"filename": file.filename, "error": "文件超过 200MB 限制"})
                continue

            filename = file.filename or "untitled"
            body = content
            processed = False

            if is_image(content):
                try:
                    body, ext = process_image(content, settings["webp_enabled"], settings["webp_quality"])
                    processed = True
                    if settings["webp_enabled"]:
                        filename = _replace_extension(filename, ext)
                except Exception:
                    pass

            url = await upload_file(body, filename, userhash)
            entry = {
                "filename": filename,
                "url": url,
                "size": len(body),
                "type": _guess_type(filename),
                "time": datetime.now(timezone.utc).isoformat(),
                "processed": processed,
            }
            results.append(entry)
            add_history(entry)

        except CatboxError as e:
            errors.append({"filename": file.filename, "error": str(e)})
        except Exception as e:
            errors.append({"filename": file.filename, "error": f"上传异常: {e}"})

    return {"ok": True, "results": results, "errors": errors, "total": len(files)}


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
