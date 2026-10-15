"""Validated settings and safe history records."""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

HISTORY_LIMIT = 500
URL_PATTERN = re.compile(r"https://files\.catbox\.moe/[A-Za-z0-9_-]+\.[A-Za-z0-9]+\Z")


def safe_url(value: str) -> str:
    if not URL_PATTERN.fullmatch(value):
        raise ValueError("只接受 files.catbox.moe 的 HTTPS 文件地址")
    return value


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    webp_enabled: bool | None = None
    webp_quality: int | None = Field(default=None, ge=1, le=100)
    upload_concurrency: int | None = Field(default=None, ge=1, le=6)
    theme: Literal["auto", "light", "dark"] | None = None


class HistoryEntry(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    url: str = Field(max_length=2048)
    filename: str = Field(default="untitled", max_length=255)
    size: int = Field(default=0, ge=0, le=2**53 - 1)
    type: Literal["image", "video", "audio", "text", "unknown"] = "unknown"
    time: str = Field(default="", max_length=64)
    processed: bool = False
    warning: str | None = Field(default=None, max_length=200)
    _url = field_validator("url")(safe_url)


class HistoryDelete(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    urls: list[str] = Field(min_length=1, max_length=HISTORY_LIMIT)

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, values):
        return [safe_url(value) for value in values]
