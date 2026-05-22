"""图片处理 —— WebP 转换与压缩"""

import io
from PIL import Image

_SUPPORTED = {"JPEG", "PNG", "BMP", "TIFF", "GIF", "WEBP", "ICO"}


def is_image(content: bytes) -> bool:
    """是否为可处理的静态图片（GIF 动图除外）"""
    try:
        img = Image.open(io.BytesIO(content))
        return img.format in _SUPPORTED and not getattr(img, "is_animated", False)
    except Exception:
        return False


def process_image(content: bytes, webp: bool = False, quality: int = 80) -> tuple[bytes, str]:
    """压缩图片，可选转为 WebP。返回 (bytes, 扩展名)"""
    img = Image.open(io.BytesIO(content))

    if getattr(img, "is_animated", False):
        return content, "gif"

    if img.mode not in ("RGB", "RGBA"):
        transparent = img.mode == "P" and img.info.get("transparency") is not None
        img = img.convert("RGBA" if transparent else "RGB")

    if webp:
        fmt, ext = "WEBP", "webp"
        kwargs = {"format": fmt, "quality": quality}
        if quality >= 90:
            kwargs["lossless"] = True
    else:
        fmt = img.format or "JPEG"
        ext = "jpg" if fmt.lower() == "jpeg" else fmt.lower()
        kwargs = {"format": fmt, "quality": quality, "optimize": True}
        if fmt == "PNG":
            kwargs = {"format": "PNG", "optimize": True}
        elif fmt == "GIF":
            kwargs = {"format": "GIF", "optimize": True}

    buf = io.BytesIO()
    img.save(buf, **kwargs)
    return buf.getvalue(), ext
