import random
from datetime import date, datetime, timedelta

from photostory.selector import History, filter_refs, photo_key, select_photos
from photostory.sources.base import PhotoRef


def refs(n, months=12):
    return [PhotoRef(id=f"p{i}", name=f"IMG_{i}.jpg", taken_at=datetime(2023 + i // 12 % 2, i % months + 1, 1)) for i in range(n)]


def test_selects_k_unique(tmp_path):
    h = History(tmp_path / "h.json")
    picked = select_photos(refs(100), 10, h, date(2026, 11, 12), 180, random.Random(0))
    assert len(picked) == 10 and len({r.id for r in picked}) == 10


def test_spreads_across_months(tmp_path):
    h = History(tmp_path / "h.json")
    picked = select_photos(refs(240, months=12), 10, h, date(2026, 11, 12), 180, random.Random(1))
    months = {r.taken_at.strftime("%Y-%m") for r in picked}
    assert len(months) == 10  # 24 month buckets available -> no month repeated


def test_avoids_recent_repeats_and_falls_back(tmp_path):
    all_refs = refs(15)
    h = History(tmp_path / "h.json")
    today = date(2026, 11, 12)
    first = select_photos(all_refs, 10, h, today, 180, random.Random(2))
    h.record(today, first, "ep1")
    h.save()

    h2 = History(tmp_path / "h.json")
    second = select_photos(all_refs, 10, h2, today + timedelta(days=7), 180, random.Random(3))
    fresh = {r.id for r in all_refs} - {r.id for r in first}
    assert fresh <= {r.id for r in second}  # all 5 unused photos are taken first
    assert len(second) == 10  # topped up from used ones


def test_history_stores_only_hashes(tmp_path):
    h = History(tmp_path / "h.json")
    h.record(date(2026, 1, 1), [PhotoRef(id="secret-onedrive-id", name="Grandma.jpg")], "t")
    h.save()
    text = (tmp_path / "h.json").read_text()
    assert "secret-onedrive-id" not in text and "Grandma" not in text
    assert photo_key("secret-onedrive-id") in text


def test_filter_refs():
    rs = [
        PhotoRef(id="1", name="Screenshot_2024.png"),
        PhotoRef(id="2", name="IMG_1.jpg", width=200, height=150),
        PhotoRef(id="3", name="IMG_2.jpg", width=4000, height=3000),
        PhotoRef(id="4", name="IMG_3.jpg"),
    ]
    assert [r.id for r in filter_refs(rs, ["screenshot"], 500)] == ["3", "4"]
