import math
import os
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from photostory.config import Config
from photostory.generator import fake_episode
from photostory.models import PhotoVoice, check_episode
from photostory.quotes import load_quotes
from photostory.render import render_episode
from photostory.voice import Clip, build_track, speaker_id_for

from .conftest import make_photos
from .test_share import needs_browser

RATE = 22050


def tone(seconds: float, freq: float = 440.0) -> Clip:
    n = int(seconds * RATE)
    pcm = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / RATE))) for i in range(n))
    return Clip(pcm=pcm, rate=RATE)


def fake_synth(text: str, speaker: str) -> Clip:
    return tone(1.0 + 0.1 * len(text.split()))


# ---------------------------------------------------------------- quotes

def test_quotes_are_well_formed():
    quotes = load_quotes()
    assert len(quotes) >= 20
    for q in quotes.values():
        assert q.text and q.author and q.source
        assert len(q.text) <= 160, "keep quotes short enough for the collage"


def test_invalid_quote_id_is_rejected():
    cfg = Config()
    ep = fake_episode(make_photos(3), cfg)
    ep.collage_quote_id = 9999
    assert any("collage_quote_id" in p for p in check_episode(ep, 3, cfg.story.quiz_questions))


# ---------------------------------------------------------------- voice lines

def test_voices_must_cover_every_photo_and_stay_short():
    cfg = Config()
    ep = fake_episode(make_photos(3), cfg)
    ep.voices = ep.voices[:2] + [PhotoVoice(photo=3, speaker="the dog", line="woof " * 30)]
    problems = check_episode(ep, 3, cfg.story.quiz_questions)
    assert any("too long" in p for p in problems)
    ep.voices = ep.voices[:2]
    assert any("voices must have one line per photo" in p for p in check_episode(ep, 3, cfg.story.quiz_questions))


def test_speaker_voice_is_stable_and_spread():
    palette = list(range(12))
    assert speaker_id_for("The Smiling Pumpkin", palette) == speaker_id_for(" the smiling pumpkin ", palette)
    labels = [f"speaker {i}" for i in range(40)]
    assert len({speaker_id_for(x, palette) for x in labels}) >= 8


def test_build_track_places_speech_inside_its_scene():
    clip = tone(1.0)
    pcm = build_track([(2.0, None, 0.0), (3.0, clip, 0.5), (1.0, None, 0.0)], RATE)
    assert len(pcm) == 6 * RATE * 2
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    sec = lambda a, b: max(abs(x) for x in samples[int(a * RATE): int(b * RATE)])  # noqa: E731
    assert sec(0, 2.4) == 0 and sec(2.6, 3.4) > 1000 and sec(3.6, 6) == 0


def test_page_has_talk_buttons_and_quote():
    cfg = Config()
    photos = make_photos(3)
    ep = fake_episode(photos, cfg)
    r = render_episode(ep, photos, __import__("datetime").date(2026, 11, 19), "Fam")
    assert r.page_html.count('class="say"') == 3 and "speechSynthesis" in r.page_html
    q = load_quotes()[ep.collage_quote_id]
    assert q.text.split(",")[0] in r.page_html and q.author in r.email_html
    assert "💬" in r.markdown


@needs_browser
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_video_speaks_each_line(tmp_path):
    from photostory.share import COLLAGE_S, ENDING_S, SONG_S, SPEECH_START, SPEECH_TAIL, TITLE_S, build_share_pack

    cfg = Config()
    photos = make_photos(3)
    ep = fake_episode(photos, cfg)
    pack = build_share_pack(ep, photos, tmp_path / "wa", chapter_seconds=2, synth=fake_synth)
    assert pack.talking
    probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type:format=duration",
                                     "-of", "default=nw=1", str(pack.video)]).decode()
    assert "codec_type=audio" in probe
    speech = fake_synth(ep.voices[0].line, "").seconds
    chapter = max(2, round(speech + SPEECH_START + SPEECH_TAIL, 2))
    expected = TITLE_S + 3 * chapter + ENDING_S + SONG_S + COLLAGE_S
    dur = float(probe.split("duration=")[1].split()[0])
    assert abs(dur - expected) < 0.5


@pytest.mark.skipif(not os.getenv("PHOTOSTORY_VOICE_MODEL"), reason="set PHOTOSTORY_VOICE_MODEL to test real Piper")
def test_real_piper_voice_speaks():
    from photostory.voice import piper_synth

    synth = piper_synth(Path(os.environ["PHOTOSTORY_VOICE_MODEL"]))
    clip = synth("Fasten your seatbelts, this pumpkin is cleared for take-off!", "the smiling pumpkin")
    samples = struct.unpack(f"<{len(clip.pcm) // 2}h", clip.pcm)
    assert 1.5 < clip.seconds < 8 and max(map(abs, samples)) > 3000
