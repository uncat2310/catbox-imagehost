"""配置管理 —— JSON 文件持久化"""

import json
from datetime import datetime, timezone
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "config"
CONFIG_FILE = CONFIG_DIR / "settings.json"

ALLOWED_SETTINGS = {"webp_enabled", "webp_quality", "theme"}
VALID_THEMES = {"auto", "light", "dark"}
KEEP_HISTORY = 200
KEEP_HISTORY_IMPORT = 500
DEFAULT_SETTINGS = {
    "webp_enabled": False,
    "webp_quality": 80,
    "theme": "auto",
}


def load() -> dict:
    """加载配置"""
    try:
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save(cfg: dict) -> None:
    """保存配置"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
    tmp.replace(CONFIG_FILE)


def _update_config(updates: dict) -> None:
    """原子更新：加载 → 修改 → 保存"""
    cfg = load()
    cfg.update(updates)
    save(cfg)


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_quality(value) -> int:
    try:
        quality = int(value)
    except (TypeError, ValueError):
        quality = DEFAULT_SETTINGS["webp_quality"]
    return max(1, min(100, quality))


def _coerce_theme(value) -> str:
    return value if value in VALID_THEMES else DEFAULT_SETTINGS["theme"]


def _normalize_settings(data: dict) -> dict:
    normalized = {}
    if "webp_enabled" in data:
        normalized["webp_enabled"] = _coerce_bool(data["webp_enabled"])
    if "webp_quality" in data:
        normalized["webp_quality"] = _coerce_quality(data["webp_quality"])
    if "theme" in data:
        normalized["theme"] = _coerce_theme(data["theme"])
    return normalized


# ── 设置读写 ──────────────────────────────────────────────

def merge_settings(data: dict) -> None:
    """合并前端提交的设置"""
    delta = _normalize_settings({k: data[k] for k in ALLOWED_SETTINGS if k in data})
    if delta:
        _update_config(delta)


def get_settings() -> dict:
    """获取全部前端用设置"""
    cfg = load()
    return {
        "webp_enabled": _coerce_bool(cfg.get("webp_enabled", DEFAULT_SETTINGS["webp_enabled"])),
        "webp_quality": _coerce_quality(cfg.get("webp_quality", DEFAULT_SETTINGS["webp_quality"])),
        "theme": _coerce_theme(cfg.get("theme", DEFAULT_SETTINGS["theme"])),
    }


# ── 历史管理 ──────────────────────────────────────────────

def get_history() -> list[dict]:
    history = load().get("history", [])
    return history if isinstance(history, list) else []


def add_history(entry: dict) -> None:
    cfg = load()
    history = cfg.get("history", [])
    if not isinstance(history, list):
        history = []
    history.insert(0, entry)
    cfg["history"] = history[:KEEP_HISTORY]
    save(cfg)


def remove_history_batch(urls: list[str]) -> int:
    cfg = load()
    history = cfg.get("history", [])
    if not isinstance(history, list):
        history = []
    before = len(history)
    exclude = set(urls)
    cfg["history"] = [h for h in history if isinstance(h, dict) and h.get("url") not in exclude]
    save(cfg)
    return before - len(cfg["history"])


# ── 导出 / 导入 ──────────────────────────────────────────

def export_data() -> dict:
    cfg = load()
    return {
        "version": "2.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "settings": get_settings(),
        "history": get_history(),
    }


def import_data(data: dict) -> dict:
    cfg = load()
    added = 0

    s = data.get("settings")
    if isinstance(s, dict):
        cfg.update(_normalize_settings({key: s[key] for key in ALLOWED_SETTINGS if s.get(key) is not None}))

    if isinstance(data.get("history"), list):
        history = cfg.get("history", [])
        if not isinstance(history, list):
            history = []
        cfg["history"] = history
        existing = {h.get("url") for h in history if isinstance(h, dict) and h.get("url")}
        for entry in data["history"]:
            if not isinstance(entry, dict):
                continue
            if entry.get("url") and entry["url"] not in existing:
                cfg.setdefault("history", []).append(entry)
                existing.add(entry["url"])
                added += 1
        cfg["history"] = cfg["history"][:KEEP_HISTORY_IMPORT]

    save(cfg)
    return {"ok": True, "imported_history": added}
