from __future__ import annotations

import io
from datetime import datetime

import pytest
from PIL import Image

from photostory.config import Config
from photostory.sources.base import Photo, PhotoRef


def jpeg_bytes(color="red", size=(800, 600)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def photo_dir(tmp_path):
    d = tmp_path / "photos"
    (d / "2024" / "summer").mkdir(parents=True)
    colors = ["red", "green", "blue", "yellow", "purple", "orange", "pink", "brown", "gray", "cyan", "navy", "olive"]
    for i, c in enumerate(colors):
        sub = d / "2024" / "summer" if i % 2 else d
        Image.new("RGB", (1200, 900), c).save(sub / f"IMG_{i:03d}.jpg")
    Image.new("RGB", (1200, 900), "white").save(d / "Screenshot 2024-01-01.png")
    (d / "notes.txt").write_text("not a photo")
    return d


@pytest.fixture
def cfg(tmp_path, photo_dir) -> Config:
    c = Config()
    c.source.type = "local"
    c.source.path = str(photo_dir)
    c.history_file = str(tmp_path / "state" / "history.json")
    c.output_dir = str(tmp_path / "out")
    c.email.to = ["family@example.com"]
    c.whatsapp.enabled = False  # rendering needs Chromium + ffmpeg; covered in test_share.py
    return c


def make_photos(n: int) -> list[Photo]:
    return [
        Photo(ref=PhotoRef(id=f"id{i}", name=f"p{i}.jpg", taken_at=datetime(2024, 1 + i % 12, 1)), jpeg=jpeg_bytes(), width=800, height=600)
        for i in range(n)
    ]
