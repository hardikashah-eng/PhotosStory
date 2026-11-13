"""Photos from a folder on disk (handy for testing, a NAS mount, or a synced OneDrive folder)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image

from ..imaging import to_jpeg
from .base import Photo, PhotoRef

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME = 306


def _taken_at(path: Path) -> datetime | None:
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            raw = exif.get_ifd(0x8769).get(_EXIF_DATETIME_ORIGINAL) or exif.get(_EXIF_DATETIME)
            if raw:
                return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return datetime.fromtimestamp(path.stat().st_mtime)


class LocalSource:
    def __init__(self, root: str | Path, max_depth: int = 4):
        self.root = Path(root).expanduser()
        self.max_depth = max_depth

    def list_photos(self) -> list[PhotoRef]:
        if not self.root.is_dir():
            raise FileNotFoundError(f"Photo folder not found: {self.root}")
        refs: list[PhotoRef] = []
        for p in sorted(self.root.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
                continue
            if len(p.relative_to(self.root).parts) - 1 > self.max_depth:
                continue
            refs.append(PhotoRef(id=str(p.relative_to(self.root)), name=p.name, taken_at=_taken_at(p)))
        return refs

    def fetch(self, ref: PhotoRef, max_side: int) -> Photo:
        jpeg, w, h = to_jpeg((self.root / ref.id).read_bytes(), max_side=max_side)
        return Photo(ref=ref, jpeg=jpeg, width=w, height=h)
