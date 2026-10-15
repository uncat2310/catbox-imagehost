"""Bounded image inspection and format-preserving compression."""
import io
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 20_000_000
SUPPORTED = {"JPEG", "PNG", "BMP", "TIFF", "GIF", "WEBP", "ICO"}


class ImageLimitError(ValueError):
    pass


def is_image(source) -> bool:
    try:
        if hasattr(source, "seek"):
            source.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(source) if isinstance(source, bytes) else source) as img:
                if img.width * img.height > MAX_PIXELS:
                    raise ImageLimitError("图片超过 2000 万像素限制")
                return img.format in SUPPORTED and not getattr(img, "is_animated", False)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageLimitError("图片像素过大") from exc
    except UnidentifiedImageError:
        return False
    finally:
        if hasattr(source, "seek") and not source.closed:
            source.seek(0)


def process_image(content: bytes, webp: bool = False, quality: int = 80) -> tuple[bytes, str]:
    with Image.open(io.BytesIO(content)) as source:
        if source.width * source.height > MAX_PIXELS:
            raise ImageLimitError("图片超过 2000 万像素限制")
        source_format = source.format
        ext = "jpg" if source_format == "JPEG" else source_format.lower()
        if getattr(source, "is_animated", False):
            return content, ext
        if not webp and source_format not in {"PNG", "JPEG", "WEBP"}:
            return content, ext
        img = ImageOps.exif_transpose(source)
        try:
            transparent = img.mode == "P" and "transparency" in img.info
            if img.mode not in {"RGB", "RGBA"}:
                img = img.convert("RGBA" if transparent else "RGB")
            fmt = "WEBP" if webp else source_format
            ext = "webp" if webp else ext
            if fmt == "JPEG" and img.mode != "RGB":
                img = img.convert("RGB")
            options = {"format": fmt, "quality": quality}
            if fmt == "PNG":
                options = {"format": fmt, "optimize": True}
            output = io.BytesIO()
            img.save(output, **options)
            return output.getvalue(), ext
        finally:
            img.close()
