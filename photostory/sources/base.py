from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class PhotoRef:
    """A photo we know about but haven't downloaded yet."""

    id: str
    name: str
    taken_at: datetime | None = None
    width: int | None = None
    height: int | None = None
    extra: dict = field(default_factory=dict, compare=False, hash=False)


@dataclass
class Photo:
    """A downloaded, normalised photo ready for the model and the renderer."""

    ref: PhotoRef
    jpeg: bytes
    width: int
    height: int


class PhotoSource(Protocol):
    def list_photos(self) -> list[PhotoRef]: ...

    def fetch(self, ref: PhotoRef, max_side: int) -> Photo: ...
