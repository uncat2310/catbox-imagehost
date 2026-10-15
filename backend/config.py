"""Transactional settings with non-destructive legacy JSON migration."""
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from pydantic import ValidationError
from backend.models import HistoryEntry, SettingsPatch, HISTORY_LIMIT

CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", Path(__file__).parent.parent / "config"))
DEFAULT_SETTINGS = {"webp_enabled": False, "webp_quality": 80, "upload_concurrency": 3, "theme": "auto"}


def _legacy():
    path = CONFIG_DIR / "settings.json"
    if not path.exists():
        return {**DEFAULT_SETTINGS, "history": []}
    raw = json.loads(path.read_text("utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("旧配置必须是 JSON 对象；请先修复或恢复备份")
    settings = dict(DEFAULT_SETTINGS)
    for key in DEFAULT_SETTINGS:
        if key in raw:
            try:
                settings.update(SettingsPatch.model_validate({key: raw[key]}).model_dump(exclude_none=True))
            except ValidationError:
                pass
    history, seen = [], set()
    for entry in raw.get("history", []) if isinstance(raw.get("history"), list) else []:
        try:
            normalized = HistoryEntry.model_validate(entry).model_dump(exclude_none=True)
        except ValidationError:
            continue
        if normalized["url"] not in seen:
            seen.add(normalized["url"])
            history.append(normalized)
    return {**settings, "history": history[:HISTORY_LIMIT]}


@contextmanager
def _transaction():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(CONFIG_DIR / "settings.db", timeout=10)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK (id=1), data TEXT NOT NULL)")
        row = connection.execute("SELECT data FROM state WHERE id=1").fetchone()
        cfg = json.loads(row[0]) if row else _legacy()
        yield cfg
        serialized = json.dumps(cfg, ensure_ascii=False)
        if not row or row[0] != serialized:
            connection.execute("INSERT OR REPLACE INTO state VALUES (1, ?)", (serialized,))


def initialize():
    with _transaction():
        pass


def get_settings():
    with _transaction() as cfg:
        return {key: cfg.get(key, default) for key, default in DEFAULT_SETTINGS.items()}


def merge_settings(data: dict):
    updates = SettingsPatch.model_validate(data).model_dump(exclude_none=True)
    with _transaction() as cfg:
        cfg.update(updates)


def get_history():
    with _transaction() as cfg:
        return list(cfg.get("history", []))


def add_history_batch(entries: list[dict]):
    validated = [HistoryEntry.model_validate(entry).model_dump(exclude_none=True) for entry in entries]
    with _transaction() as cfg:
        seen = {entry["url"] for entry in validated}
        cfg["history"] = (list(reversed(validated)) + [entry for entry in cfg.get("history", []) if entry["url"] not in seen])[:HISTORY_LIMIT]


def remove_history_batch(urls: list[str]):
    with _transaction() as cfg:
        before = len(cfg.get("history", []))
        exclude = set(urls)
        cfg["history"] = [entry for entry in cfg.get("history", []) if entry["url"] not in exclude]
        return before - len(cfg["history"])
