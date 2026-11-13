"""Image normalisation: any input (JPEG/PNG/HEIC/...) -> upright, resized RGB JPEG."""

from __future__ import annotations

import io

from PIL import Image, ImageOps

try:  # Optional HEIC support for iPhone photos in local folders.
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass


def to_jpeg(data: bytes, max_side: int = 1280, quality: int = 85) -> tuple[bytes, int, int]:
    """Return (jpeg_bytes, width, height) with EXIF rotation applied and metadata stripped.

    Stripping EXIF also drops GPS coordinates, so nothing location-revealing
    is sent to the model or embedded in the emailed episode.
    """
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        out = io.BytesIO()
        im.convert("RGB").save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue(), im.width, im.height
