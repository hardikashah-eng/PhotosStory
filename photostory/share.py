"""WhatsApp share pack: swipeable story cards, ready-to-paste quiz polls, and a short video.

WhatsApp handles an .html file badly (it arrives as a "document"), so each episode is
also turned into formats that play natively in a chat:

- cards/NN_*.jpg   1080x1350 (4:5) images: title, one per chapter, ending + quiz teaser, song,
                   and a family collage (timeline of every photo with year stickers)
- polls.txt        the quiz as WhatsApp polls (question + options) plus an answer-reveal message
- photostory.mp4   ~60 s slideshow: slow zoom on each photo, caption fade-in, dip-to-black cuts

Cards and video frames are drawn with headless Chromium (Playwright) so emoji and
typography render properly; the video is encoded with ffmpeg (H.264, ~5 MB).
Install with `pip install ".[share]" && python -m playwright install chromium`.
"""

from __future__ import annotations

import base64
import html
import io
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .models import Episode
from .render import cover_photo
from .sources.base import Photo

log = logging.getLogger(__name__)

W, H, FPS = 1080, 1350, 30
SANS = '-apple-system,"Segoe UI",Roboto,Arial,sans-serif'
POLL_QUESTION_MAX, POLL_OPTION_MAX = 255, 100  # WhatsApp limits

_e = html.escape


def _uri(p: Photo) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.jpeg).decode()


def _lines(text: str) -> str:
    return "<br>".join(_e(line) for line in text.splitlines())


@dataclass
class SharePack:
    dir: Path
    cards: list[Path] = field(default_factory=list)
    polls: Path | None = None
    video: Path | None = None
    collage: Path | None = None

    def files(self) -> list[Path]:
        return [p for p in [self.video, *self.cards, self.polls] if p]


# ---------------------------------------------------------------- polls

def polls_text(ep: Episode) -> str:
    out = [
        "THURSDAY PHOTOSTORY — WHATSAPP POLLS",
        'In WhatsApp: 📎 → Poll. Paste the question, add each option, and turn OFF "Allow multiple answers".',
        "",
    ]
    for i, q in enumerate(ep.quiz, 1):
        out += [f"POLL {i}", f"Question: {q.question[:POLL_QUESTION_MAX]}"]
        out += [f"  Option: {o[:POLL_OPTION_MAX]}" for o in q.options] + [""]
    out += ["ANSWER REVEAL (send this the next day 🙈)", ""]
    out += [f"{i}. {q.options[q.answer]} — {q.explanation}" for i, q in enumerate(ep.quiz, 1)]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- cards

_CARD_CSS = f"""
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{W}px;height:{H}px;overflow:hidden;font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;color:#2b2420}}
.card{{width:{W}px;height:{H}px;position:relative;background:#fbf6ec;padding:64px 70px;display:flex;flex-direction:column;align-items:center}}
.dark{{background:#2b2420;color:#fbf6ec}}
.kicker{{font:700 26px/1 {SANS};letter-spacing:.16em;text-transform:uppercase;color:#d9572b}}
.mid{{flex:1;display:flex;align-items:center;justify-content:center;width:100%}}
.pol{{background:#fff;padding:20px 20px 22px;box-shadow:0 14px 40px rgba(43,36,32,.18);margin:26px 0;display:flex;flex-direction:column;align-items:center}}
.pol img{{display:block;max-width:900px;max-height:640px;width:auto;height:auto}}
.cap{{font-family:"Segoe Print","Bradley Hand","Comic Neue","Comic Sans MS",cursive;font-size:34px;line-height:1.3;text-align:center;padding:18px 10px 0;max-width:900px}}
.body{{width:100%;margin-bottom:34px}}
h2{{font-size:52px;line-height:1.12;margin:0 0 14px}}
p.t{{font-size:36px;line-height:1.42}}
.foot{{position:absolute;left:0;right:0;bottom:30px;text-align:center;font:600 22px/1 {SANS};color:#9a8d80;letter-spacing:.06em}}
"""


def _page(inner: str, cls: str = "") -> str:
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{_CARD_CSS}</style></head><body><div class='card {cls}'>{inner}</div></body></html>"


def card_pages(ep: Episode, photos: list[Photo]) -> list[tuple[str, str]]:
    """(file stem, HTML) for every card, in album order."""
    caps = {c.photo: c for c in ep.captions}
    title = _e(ep.title)
    foot = f"<div class='foot'>🎬 {title}</div>"
    pages = [(
        "00_title",
        _page(f"""
  <div class='kicker'>Thursday PhotoStory · This week</div>
  <h1 style='font-size:84px;line-height:1.05;text-align:center;margin-top:30px'>{title}</h1>
  <p style='font-size:34px;line-height:1.4;font-style:italic;color:#7a6e64;text-align:center;margin-top:22px;max-width:900px'>{_e(ep.tagline)}</p>
  <div class='pol' style='transform:rotate(-2deg);margin-top:44px'><img src='{_uri(cover_photo(ep, photos))}' style='max-height:560px'></div>
  <div style='margin-top:auto;font:700 32px/1.3 {SANS};background:#2b2420;color:#fbf6ec;padding:18px 34px;border-radius:99px'>Swipe ➜ {len(ep.story)} chapters · quiz · sing-along</div>"""),
    )]
    n = len(ep.story)
    for i, b in enumerate(ep.story, 1):
        c = caps[b.photo]
        rot = -1.6 if i % 2 else 1.4
        pages.append((
            f"{i:02d}_chapter",
            _page(f"""
  <div class='kicker'>Chapter {i} of {n}</div>
  <div class='mid'><div class='pol' style='transform:rotate({rot}deg)'><img src='{_uri(photos[b.photo - 1])}'><div class='cap'>{_e(c.caption)} {_e(c.emoji)}</div></div></div>
  <div class='body'><h2>{_e(b.heading)}</h2><p class='t'>{_e(b.text)}</p></div>{foot}"""),
        ))
    pages.append((
        f"{n + 1:02d}_ending",
        _page(f"""
  <div class='kicker'>The End… for now</div>
  <p style='font-size:42px;line-height:1.5;margin-top:70px'>{_e(ep.story_ending)}</p>
  <p style='font-size:34px;line-height:1.45;font-style:italic;color:#7a6e64;margin-top:40px'>🔮 {_e(ep.next_week_teaser)}</p>
  <div style='margin-top:auto;margin-bottom:40px;width:100%;background:#fde3d6;border-radius:28px;padding:40px 44px'>
    <div style='font-size:56px;font-weight:700'>🧠 Quiz time!</div>
    <p style='font-size:34px;line-height:1.45;margin-top:10px'>{len(ep.quiz)} questions are waiting in the polls below. Kids vs. grown-ups: who remembers the most?</p>
  </div>{foot}"""),
    ))
    s = ep.song
    cells = "".join(
        f"<div><div style='font:600 22px/1 Arial,sans-serif;letter-spacing:.14em;opacity:.6;margin-bottom:10px'>VERSE {k}</div>"
        f"<div style='font-size:34px;line-height:1.4'>{_lines(v)}</div></div>"
        for k, v in enumerate(s.verses, 1)
    )
    if len(s.verses) % 2:
        cells += (f"<div style='align-self:center;font:400 28px/1.45 {SANS};opacity:.8'>"
                  "🎶 Sing the chorus after every verse, then clap twice 👏👏</div>")
    pages.append((
        f"{n + 2:02d}_song",
        _page(f"""
  <div class='kicker' style='color:#ffcf8a'>🎤 Sing-along</div>
  <h1 style='font-size:66px;margin:20px 0 8px;text-align:center'>{_e(s.title)}</h1>
  <p style='font:400 27px/1.4 {SANS};opacity:.75;text-align:center;max-width:940px'>{_e(s.style)} · {_e(s.tune_hint)}</p>
  <div style='width:100%;margin-top:36px;border:4px solid #ffcf8a;border-radius:26px;padding:26px 36px;color:#ffcf8a;text-align:center'>
    <div style='font:700 22px/1 Arial,sans-serif;letter-spacing:.16em;margin-bottom:14px'>CHORUS · EVERYBODY!</div>
    <div style='font-size:46px;line-height:1.3;font-weight:700'>{_lines(s.chorus)}</div>
  </div>
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:34px 56px;width:100%;margin-top:40px'>{cells}</div>
  <div class='foot' style='color:#8c8178'>🎬 {title}</div>""", "dark"),
    ))
    pages.append((f"{n + 3:02d}_collage", collage_page(ep, photos)))
    return pages


# ---------------------------------------------------------------- collage

def _rows(n: int) -> list[int]:
    """Split n photos into rows of 2-4, longer rows in the middle (10 -> [3, 4, 3])."""
    if n <= 4:
        return [n]
    r = -(-n // 4)  # ceil
    base, extra = divmod(n, r)
    rows = [base] * r
    mid = r // 2
    for k in range(extra):  # hand extras to the middle rows first
        rows[(mid + (k + 1) // 2 * (-1) ** k) % r] += 1
    return rows


def collage_title(photos: list[Photo]) -> tuple[str, str]:
    years = sorted({p.ref.taken_at.year for p in photos if p.ref.taken_at})
    if len(years) >= 2 and years[-1] - years[0] >= 2:
        return f"{years[-1] - years[0]} Years of Us", f"{years[0]} — {years[-1]}"
    if years:
        return "Our Memories", str(years[0]) if len(years) == 1 else f"{years[0]} — {years[-1]}"
    return "Our Memories", "This week's photos"


def collage_page(ep: Episode, photos: list[Photo]) -> str:
    """Scrapbook timeline of every photo in the episode, oldest first, with year stickers."""
    ordered = sorted(photos, key=lambda p: (p.ref.taken_at is None, p.ref.taken_at or 0))
    title, span = collage_title(photos)
    rows = _rows(len(ordered))
    usable_w, gap = 960, 22
    row_h = min(300, (800 - gap * (len(rows) - 1)) / len(rows))
    tilts = [-3.2, 2.4, -1.4, 3.0, -2.6, 1.6, -0.8, 2.8, -3.4, 1.2, -2.0, 2.2]
    html_rows, k = [], 0
    for cols in rows:
        w = min((usable_w - gap * (cols - 1)) / cols, (row_h - 24) * 4 / 3 + 24)
        tiles = []
        for _ in range(cols):
            p = ordered[k]
            year = p.ref.taken_at.year if p.ref.taken_at else ""
            sticker = (f"<div style='position:absolute;left:-10px;bottom:-12px;background:#d9572b;color:#fff;"
                       f"font:800 {max(18, int(w / 11))}px/1 {SANS};padding:7px 12px;border-radius:10px;"
                       f"box-shadow:0 3px 8px rgba(0,0,0,.2);transform:rotate(-4deg)'>{year}</div>") if year else ""
            tiles.append(
                f"<div style='position:relative;background:#fff;padding:10px;width:{w:.0f}px;"
                f"box-shadow:0 8px 22px rgba(43,36,32,.22);transform:rotate({tilts[k % len(tilts)]}deg)'>"
                f"<div style='width:100%;aspect-ratio:4/3;background:url({_uri(p)}) center 30%/cover'></div>{sticker}</div>"
            )
            k += 1
        html_rows.append(f"<div style='display:flex;justify-content:center;gap:{gap}px'>{''.join(tiles)}</div>")
    return _page(f"""
  <div class='kicker'>Thursday PhotoStory · Our memories</div>
  <h1 style='font-size:80px;line-height:1.05;text-align:center;margin-top:20px'>{_e(title)}</h1>
  <div style='font:700 28px/1 {SANS};letter-spacing:.2em;color:#7a6e64;margin-top:14px'>{_e(span)}</div>
  <div style='flex:1;display:flex;flex-direction:column;justify-content:center;gap:{gap + 8}px;width:100%'>{''.join(html_rows)}</div>
  <p style='font-size:38px;line-height:1.4;font-style:italic;text-align:center;max-width:920px;margin-bottom:40px'>❤️ {_e(ep.collage_message)}</p>
  <div class='foot'>🎬 {_e(ep.title)}</div>""")


# ---------------------------------------------------------------- video layers

def _photo_layer(p: Photo) -> str:
    return f"""<html><body style='margin:0;width:{W}px;height:{H}px;overflow:hidden;background:#000'>
<div style='position:absolute;inset:-60px;background:url({_uri(p)}) center/cover;filter:blur(40px) brightness(.55)'></div>
<img src='{_uri(p)}' style='position:absolute;left:0;right:0;top:0;bottom:250px;margin:auto;max-width:{W}px;max-height:1100px;box-shadow:0 20px 60px rgba(0,0,0,.5)'>
</body></html>"""


def _text_layer(kicker: str, heading: str, caption: str) -> str:
    return f"""<html><body style='margin:0;width:{W}px;height:{H}px;background:transparent'>
<div style='position:absolute;left:0;right:0;bottom:0;height:520px;background:linear-gradient(transparent,rgba(20,14,10,.92) 45%)'></div>
<div style='position:absolute;left:64px;right:64px;bottom:70px;color:#fff;font-family:"Iowan Old Style",Palatino,Georgia,serif'>
  <div style='font:800 26px/1 {SANS};letter-spacing:.18em;color:#ffb38a;text-transform:uppercase'>{_e(kicker)}</div>
  <div style='font-size:56px;font-weight:700;line-height:1.1;margin:14px 0'>{_e(heading)}</div>
  <div style='font-family:"Segoe Print","Bradley Hand","Comic Sans MS",cursive;font-size:38px;line-height:1.32'>{_e(caption)}</div>
</div></body></html>"""


# ---------------------------------------------------------------- ffmpeg

_ENC = ["-c:v", "libx264", "-crf", "24", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]


def _ffmpeg(args: list[str], out: Path) -> None:
    tmp = out.with_name("tmp_" + out.name)  # still ends in .mp4; renamed only on success
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args, *_ENC, str(tmp)], check=True)
    tmp.replace(out)


def _zoom_scene(img: Path, seconds: float, out: Path, zoom: float = 0.04) -> None:
    f = int(seconds * FPS)
    vf = (f"scale={W * 2}:{H * 2},zoompan=z='1+{zoom}*on/{f}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={f}:s={W}x{H}:fps={FPS},fade=in:st=0:d=0.35,fade=out:st={seconds - 0.35}:d=0.35,format=yuv420p")
    _ffmpeg(["-i", str(img), "-vf", vf, "-frames:v", str(f)], out)


def _still_scene(img: Path, seconds: float, out: Path) -> None:
    vf = (f"scale={W}:{H},format=yuv420p,loop=-1:1,trim=duration={seconds},"
          f"fade=in:st=0:d=0.35,fade=out:st={seconds - 0.35}:d=0.35")
    _ffmpeg(["-framerate", str(FPS), "-i", str(img), "-vf", vf], out)


def _chapter_scene(photo: Path, text: Path, seconds: float, out: Path) -> None:
    f = int(seconds * FPS)
    fc = (f"[0]zoompan=z='1+0.06*on/{f}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={f}:s={W}x{H}:fps={FPS}[bg];"
          f"[1]loop=-1:1,trim=duration={seconds},format=rgba,fade=in:st=0.5:d=0.6:alpha=1[tx];"
          f"[bg][tx]overlay=0:0:shortest=1,fade=in:st=0:d=0.35,fade=out:st={seconds - 0.35}:d=0.35,format=yuv420p")
    _ffmpeg(["-i", str(photo), "-framerate", str(FPS), "-i", str(text), "-filter_complex", fc, "-frames:v", str(f)], out)


# ---------------------------------------------------------------- build

def _launch(pw):
    return pw.chromium.launch(executable_path=os.getenv("PHOTOSTORY_CHROME") or None)


def build_share_pack(ep: Episode, photos: list[Photo], out_dir: Path, video: bool = True,
                     chapter_seconds: float = 5.0) -> SharePack:
    from playwright.sync_api import sync_playwright

    out_dir = Path(out_dir)
    cards_dir = out_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    pack = SharePack(dir=out_dir)

    pack.polls = out_dir / "polls.txt"
    pack.polls.write_text(polls_text(ep))

    caps = {c.photo: c for c in ep.captions}
    want_video = video and shutil.which("ffmpeg") is not None
    if video and not want_video:
        log.warning("ffmpeg not found — skipping the video.")

    with tempfile.TemporaryDirectory() as tmpd, sync_playwright() as pw:
        tmp = Path(tmpd)
        browser = _launch(pw)
        try:
            page = browser.new_page(viewport={"width": W, "height": H})
            for stem, doc in card_pages(ep, photos):
                page.set_content(doc)
                page.wait_for_timeout(100)
                path = cards_dir / f"{stem}.jpg"
                Image.open(io.BytesIO(page.screenshot())).convert("RGB").save(path, quality=86, optimize=True)
                pack.cards.append(path)
            by_kind = {p.stem.split("_", 1)[1]: p for p in pack.cards}
            pack.collage = by_kind.get("collage")

            if want_video:
                big = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
                scenes: list[Path] = []
                _zoom_scene(pack.cards[0], 4, s := tmp / "s00.mp4"); scenes.append(s)
                for i, b in enumerate(ep.story, 1):
                    big.set_content(_photo_layer(photos[b.photo - 1])); big.wait_for_timeout(150)
                    photo_img = tmp / f"p{i:02d}.jpg"
                    big.screenshot(path=str(photo_img), type="jpeg", quality=92)
                    c = caps[b.photo]
                    page.set_content(_text_layer(f"Chapter {i} of {len(ep.story)}", b.heading, f"{c.caption} {c.emoji}"))
                    page.wait_for_timeout(80)
                    text_img = tmp / f"t{i:02d}.png"
                    page.screenshot(path=str(text_img), omit_background=True)
                    _chapter_scene(photo_img, text_img, chapter_seconds, s := tmp / f"s{i:02d}.mp4"); scenes.append(s)
                _zoom_scene(by_kind["ending"], 4, s := tmp / "s97.mp4"); scenes.append(s)   # ending + quiz teaser
                _still_scene(by_kind["song"], 7, s := tmp / "s98.mp4"); scenes.append(s)     # song: hold to read
                _zoom_scene(by_kind["collage"], 5, s := tmp / "s99.mp4", zoom=0.03); scenes.append(s)  # finale
                (tmp / "list.txt").write_text("".join(f"file '{p}'\n" for p in scenes))
                pack.video = out_dir / "photostory.mp4"
                tmpv = out_dir / "tmp_photostory.mp4"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i",
                                str(tmp / "list.txt"), "-c", "copy", "-movflags", "+faststart", str(tmpv)], check=True)
                tmpv.replace(pack.video)
        finally:
            browser.close()
    return pack
