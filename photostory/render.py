"""Turn an Episode + photos into: interactive HTML page, email HTML, Markdown and JSON."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup, escape

from .models import Episode
from .sources.base import Photo


def _nl2br(value: str) -> Markup:
    return Markup("<br>".join(escape(line) for line in str(value).split("\n")))


_env = Environment(loader=PackageLoader("photostory", "templates"), autoescape=select_autoescape(["j2", "html"]))
_env.filters["nl2br"] = _nl2br


def cid_for(n: int) -> str:
    return f"photo{n}@photostory"


@dataclass
class Rendered:
    page_html: str  # standalone, images embedded, interactive quiz
    email_html: str  # email-safe, images referenced by cid
    markdown: str
    json: str


def render_episode(
    ep: Episode,
    photos: list[Photo],
    episode_date: date,
    family_name: str,
    attached: bool = True,
    cover_url: str | None = None,
) -> Rendered:
    captions = {c.photo: c for c in ep.captions}
    voices = {v.photo: v for v in ep.voices}
    from .quotes import load_quotes

    quote = load_quotes().get(ep.collage_quote_id)
    data_uris = {i: "data:image/jpeg;base64," + base64.b64encode(p.jpeg).decode() for i, p in enumerate(photos, 1)}
    ctx = dict(
        ep=ep,
        captions=captions,
        family_name=family_name,
        date_label=episode_date.strftime("%A, %B %-d, %Y"),
        attached=attached,
        cover_url=cover_url,
        voices=voices,
        quote=quote,
    )
    page = _env.get_template("episode.html.j2").render(photo_src=lambda n: data_uris[n], **ctx)
    email = _env.get_template("email.html.j2").render(cid=cid_for, **ctx)
    return Rendered(page_html=page, email_html=email, markdown=to_markdown(ep, episode_date), json=ep.model_dump_json(indent=2))


def cover_photo(ep: Episode, photos: list[Photo]) -> Photo:
    """The photo that opens the story — used for the link preview and the email."""
    return photos[ep.story[0].photo - 1] if ep.story else photos[0]


@dataclass
class LinkEmail:
    html: str
    text: str
    share_text: str
    whatsapp_url: str


def render_link_email(
    ep: Episode, episode_date: date, page_url: str, expires: date | None = None, pack_note: str | None = None
) -> LinkEmail:
    share_text = f"🎬 Thursday PhotoStory: {ep.title}\n{ep.tagline}\nStory, quiz & sing-along 👉 {page_url}"
    whatsapp_url = "https://wa.me/?text=" + quote(share_text)
    html = _env.get_template("link_email.html.j2").render(
        ep=ep,
        page_url=page_url,
        share_text=share_text,
        whatsapp_url=whatsapp_url,
        date_label=episode_date.strftime("%A, %B %-d"),
        expires=expires.strftime("%A, %B %-d") if expires else None,
        pack_note=pack_note,
    )
    text = f"{share_text}\n\nShare on WhatsApp: {whatsapp_url}\n"
    return LinkEmail(html=html, text=text, share_text=share_text, whatsapp_url=whatsapp_url)


def to_markdown(ep: Episode, episode_date: date) -> str:
    caps = {c.photo: c for c in ep.captions}
    voices = {v.photo: v for v in ep.voices}
    lines = [f"# {ep.title}", f"*{ep.tagline}* — {episode_date.isoformat()}", "", f"**Premise:** {ep.theme}", "",
             "## Story", ep.story_intro, ""]
    for i, b in enumerate(ep.story, 1):
        c = caps[b.photo]
        lines += [f"### {i}. {b.heading}", f"> 📷 Photo {b.photo}: {c.caption} {c.emoji}", "", b.text, ""]
        if v := voices.get(b.photo):
            lines += [f"💬 *{v.speaker}:* “{v.line}”", ""]
    lines += [ep.story_ending, "", "## Quiz"]
    for i, q in enumerate(ep.quiz, 1):
        lines.append(f"{i}. {q.question}")
        lines += [f"   - {'ABCD'[j]}. {o}" for j, o in enumerate(q.options)]
    lines += ["", "<details><summary>Answers</summary>", ""]
    lines += [f"{i}. {'ABCD'[q.answer]} — {q.explanation}" for i, q in enumerate(ep.quiz, 1)]
    lines += ["", "</details>", "", f"## 🎤 {ep.song.title}", f"*{ep.song.style} — {ep.song.tune_hint}*", ""]
    for i, v in enumerate(ep.song.verses, 1):
        lines += [f"**Verse {i}**", v.replace("\n", "  \n"), "", "**Chorus**", ep.song.chorus.replace("\n", "  \n"), ""]
    lines += [f"🔮 {ep.next_week_teaser}", ""]
    return "\n".join(lines)


def write_outputs(r: Rendered, photos: list[Photo], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "photostory.html").write_text(r.page_html)
    (out_dir / "email.html").write_text(r.email_html)
    (out_dir / "episode.md").write_text(r.markdown)
    (out_dir / "episode.json").write_text(r.json)
    (out_dir / "photos.json").write_text(
        json.dumps([{"n": i, "name": p.ref.name} for i, p in enumerate(photos, 1)], indent=2)
    )
    return out_dir
