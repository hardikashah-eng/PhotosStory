import os
import random
import shutil
import subprocess
from datetime import date
from email import message_from_bytes, policy

import pytest

from photostory.config import Config, Secrets
from photostory.generator import fake_episode
from photostory.models import QuizQuestion
from photostory.share import card_pages, polls_text

from .conftest import make_photos


def _chromium_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            pw.chromium.launch(executable_path=os.getenv("PHOTOSTORY_CHROME") or None).close()
        return True
    except Exception:
        return False


needs_browser = pytest.mark.skipif(not _chromium_ok(), reason="Chromium for Playwright not available")


def test_polls_text_has_every_question_and_answer():
    cfg = Config()
    ep = fake_episode(make_photos(4), cfg)
    txt = polls_text(ep)
    assert txt.count("POLL ") == len(ep.quiz)
    for i, q in enumerate(ep.quiz, 1):
        assert f"Question: {q.question}" in txt
        assert f"{i}. {q.options[q.answer]} — " in txt


def test_polls_respect_whatsapp_limits():
    cfg = Config()
    ep = fake_episode(make_photos(3), cfg)
    ep.quiz[0] = QuizQuestion(question="Q" * 400, options=["a" * 150, "b", "c"], answer=1, explanation="x")
    txt = polls_text(ep)
    assert "Q" * 256 not in txt and "a" * 101 not in txt


def test_card_pages_order_and_escaping():
    cfg = Config()
    photos = make_photos(5)
    ep = fake_episode(photos, cfg)
    ep.title = "<b>bold</b> & co"
    pages = card_pages(ep, photos)
    assert [n for n, _ in pages] == ["00_title", "01_chapter", "02_chapter", "03_chapter", "04_chapter",
                                     "05_chapter", "06_ending", "07_song"]
    assert all("<b>bold</b>" not in html for _, html in pages)


@needs_browser
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_full_run_builds_pack_and_attaches_it(cfg):
    from photostory.cli import run_episode
    from photostory.deliver import EmailChannel
    from photostory.sources.local import LocalSource

    from .test_pipeline import FakeSMTP

    cfg.whatsapp.enabled = True
    cfg.whatsapp.chapter_seconds = 2
    cfg.story.photo_count = 3
    FakeSMTP.sent.clear()
    ch = EmailChannel(cfg, Secrets(smtp_username="me@x.com", smtp_password="pw"), smtp_factory=FakeSMTP)
    res = run_episode(cfg, source=LocalSource(cfg.source.path), client=None, channels=[ch],
                      today=date(2026, 11, 19), rng=random.Random(0))

    pack = res.share
    assert pack and len(pack.cards) == 3 + 3  # title + 3 chapters + ending + song
    from PIL import Image
    assert all(Image.open(c).size == (1080, 1350) for c in pack.cards)
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", str(pack.video)]))
    assert abs(dur - (4 + 3 * 2 + 4 + 7)) < 0.5

    msg = message_from_bytes(FakeSMTP.sent[0].as_bytes(), policy=policy.default)
    names = {p.get_filename() for p in msg.walk() if p.get_filename()}
    assert {"photostory.mp4", "polls.txt", "00_title.jpg"} <= names
