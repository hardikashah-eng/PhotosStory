"""Pick a varied, not-recently-used set of photos, and remember what was used.

History stores only truncated SHA-256 digests of photo ids, so committing
state/history.json to a repo reveals nothing about the photos themselves.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .sources.base import PhotoRef


def photo_key(photo_id: str) -> str:
    return hashlib.sha256(photo_id.encode()).hexdigest()[:16]


class History:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.episodes: list[dict] = []
        if self.path.exists():
            self.episodes = json.loads(self.path.read_text() or "{}").get("episodes", [])

    def last_used(self) -> dict[str, date]:
        used: dict[str, date] = {}
        for ep in self.episodes:
            d = date.fromisoformat(ep["date"])
            for k in ep.get("photos", []):
                if k not in used or used[k] < d:
                    used[k] = d
        return used

    def record(self, episode_date: date, refs: list[PhotoRef], title: str) -> None:
        self.episodes.append(
            {"date": episode_date.isoformat(), "title": title, "photos": [photo_key(r.id) for r in refs]}
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"episodes": self.episodes}, indent=2, ensure_ascii=False) + "\n")


def filter_refs(refs: list[PhotoRef], exclude_patterns: list[str], min_side_px: int) -> list[PhotoRef]:
    pats = [p.lower() for p in exclude_patterns]
    out = []
    for r in refs:
        if any(p in r.name.lower() for p in pats):
            continue
        if r.width and r.height and max(r.width, r.height) < min_side_px:
            continue
        out.append(r)
    return out


def select_photos(
    refs: list[PhotoRef],
    k: int,
    history: History,
    today: date,
    avoid_repeat_days: int,
    rng: random.Random,
) -> list[PhotoRef]:
    """Return up to k photos in a random order.

    1. Prefer photos not used in the last `avoid_repeat_days`; if there aren't
       enough, top up with the least-recently-used ones.
    2. Spread picks across different months so one birthday party doesn't
       take over the whole episode.
    """
    used = history.last_used()
    cutoff = today - timedelta(days=avoid_repeat_days)
    fresh = [r for r in refs if used.get(photo_key(r.id), date.min) < cutoff]
    picked = _diverse_sample(fresh, k, rng)

    if len(picked) < k:
        chosen = {r.id for r in picked}
        stale = sorted(
            (r for r in refs if r.id not in chosen),
            key=lambda r: (used.get(photo_key(r.id), date.min), rng.random()),
        )
        picked += stale[: k - len(picked)]
    rng.shuffle(picked)
    return picked


def _diverse_sample(refs: list[PhotoRef], k: int, rng: random.Random) -> list[PhotoRef]:
    buckets: dict[str, list[PhotoRef]] = defaultdict(list)
    for r in refs:
        buckets[r.taken_at.strftime("%Y-%m") if r.taken_at else "unknown"].append(r)
    for b in buckets.values():
        rng.shuffle(b)
    keys = list(buckets)
    rng.shuffle(keys)
    picked: list[PhotoRef] = []
    while len(picked) < k and keys:
        for key in list(keys):
            if len(picked) >= k:
                break
            if buckets[key]:
                picked.append(buckets[key].pop())
            else:
                keys.remove(key)
    return picked
