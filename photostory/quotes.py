"""Curated, attribution-checked quotes for the family collage (see data/quotes.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

import yaml


@dataclass(frozen=True)
class Quote:
    id: int
    text: str
    author: str
    source: str
    tags: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def load_quotes() -> dict[int, Quote]:
    raw = yaml.safe_load(resources.files("photostory").joinpath("data/quotes.yaml").read_text())
    return {
        q["id"]: Quote(id=q["id"], text=q["text"], author=q["author"], source=q.get("source", ""), tags=tuple(q.get("tags", [])))
        for q in raw["quotes"]
    }


def quotes_prompt() -> str:
    """The list Claude chooses from, one per line."""
    return "\n".join(f"{q.id}: “{q.text}” — {q.author} [{', '.join(q.tags)}]" for q in load_quotes().values())
