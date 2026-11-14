"""Command line: `photostory run`, `photostory onedrive-login`, `photostory list`."""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .config import Config, Secrets, load_config
from .deliver import Channel, Delivery, make_channels
from .generator import fake_episode, generate_episode, shuffle_quiz
from .models import Episode
from .publish import Publisher
from .render import cover_photo, render_episode, render_link_email, write_outputs
from .share import SharePack  # noqa: F401  (type only; rendering deps load lazily)
from .selector import History, filter_refs, select_photos
from .sources import PhotoSource, make_source
from .sources.base import Photo

log = logging.getLogger("photostory")
EXTRA_CANDIDATES = 5  # spare picks in case a download fails


def fetch_photos(source: PhotoSource, cfg: Config, today: date, history: History, rng: random.Random) -> list[Photo]:
    refs = filter_refs(source.list_photos(), cfg.source.exclude_patterns, cfg.source.min_side_px)
    log.info("Found %d candidate photos", len(refs))
    k = cfg.story.photo_count
    picks = select_photos(refs, k + EXTRA_CANDIDATES, history, today, cfg.story.avoid_repeat_days, rng)
    photos: list[Photo] = []
    for ref in picks:
        if len(photos) == k:
            break
        try:
            photos.append(source.fetch(ref, cfg.llm.image_max_side))
        except Exception as e:  # one bad file shouldn't ruin Thursday
            log.warning("Skipping %s: %s", ref.name, e)
    if len(photos) < 3:
        raise RuntimeError(f"Only {len(photos)} usable photos found — need at least 3.")
    return photos


@dataclass
class RunResult:
    episode: Episode
    out_dir: Path
    link: str | None = None
    share: "SharePack | None" = None


def run_episode(
    cfg: Config,
    *,
    source: PhotoSource,
    client,  # anthropic.Anthropic or None when fake
    channels: list[Channel],
    today: date,
    rng: random.Random,
    dry_run: bool = False,
    publisher: Publisher | None = None,
) -> RunResult:
    history = History(cfg.history_file)
    photos = fetch_photos(source, cfg, today, history, rng)
    log.info("Writing episode from %d photos", len(photos))
    ep = fake_episode(photos, cfg) if client is None else generate_episode(photos, cfg, client, rng)
    ep = shuffle_quiz(ep, rng)
    cover = cover_photo(ep, photos)

    plan = publisher.plan(today) if (publisher and not dry_run) else None
    rendered = render_episode(
        ep, photos, today, cfg.story.family_name,
        attached=cfg.email.attach_interactive_page,
        cover_url=plan.cover_url if plan else None,
    )
    out = write_outputs(rendered, photos, Path(cfg.output_dir) / today.isoformat())
    log.info("Episode '%s' written to %s", ep.title, out)

    share = None
    if cfg.whatsapp.enabled:
        try:
            from .share import build_share_pack

            synth = None
            if cfg.voices.enabled and cfg.whatsapp.video:
                from .voice import make_synth

                v = cfg.voices
                synth = make_synth(v.model_url, v.cache_dir, v.speaker_ids, v.length_scale)
            share = build_share_pack(ep, photos, out / "whatsapp", video=cfg.whatsapp.video,
                                     chapter_seconds=cfg.whatsapp.chapter_seconds, synth=synth)
            log.info("WhatsApp pack: %d cards, video=%s, talking=%s", len(share.cards), bool(share.video), share.talking)
        except Exception as e:  # optional extra: never block Thursday
            log.warning("Skipping WhatsApp pack (%s). Install with: pip install '.[share]' && "
                        "python -m playwright install chromium", e)

    if dry_run:
        log.info("Dry run: not publishing, not sending, not updating history.")
        return RunResult(ep, out, share=share)

    link = None
    if plan:
        try:
            publisher.upload(plan, rendered.page_html, cover.jpeg)
            expires = today + timedelta(days=cfg.publish.link_expiry_days) if publisher.mode == "presigned" else None
            note = None
            if share and cfg.whatsapp.attach_to_email:
                note = (("a short video, " if share.video else "") + f"{len(share.cards)} story cards to send as one album, "
                        "and polls.txt with the quiz as WhatsApp polls.")
            link = render_link_email(ep, today, plan.page_url, expires, pack_note=note)
            log.info("Published episode page (%s link).", publisher.mode)  # never log the URL itself
        except Exception as e:  # still deliver Thursday's episode, just the long way
            log.error("Publishing failed (%s); sending the full episode instead.", e)

    delivery = Delivery(ep=ep, rendered=rendered, photos=photos, cover=cover, link=link, share=share)
    for ch in channels:
        ch.send(delivery)
        log.info("Sent via %s (%s)", ch.name, "link" if link else "full episode")
    history.record(today, [p.ref for p in photos], ep.title)
    history.save()
    return RunResult(ep, out, plan.page_url if link else None, share)


def _persist_rotated_token(source: PhotoSource) -> None:
    token = getattr(source, "rotated_refresh_token", None)
    path = os.getenv("PHOTOSTORY_TOKEN_OUT")
    if token and path:
        Path(path).write_text(token)
        os.chmod(path, 0o600)


def cmd_run(args) -> int:
    cfg = load_config(args.config)
    if args.source_path:
        cfg.source.type, cfg.source.path = "local", args.source_path
    secrets = Secrets.from_env()
    source = make_source(cfg, secrets)
    _persist_rotated_token(source)  # persist early: the old token may already be spent

    client = None
    if not args.fake_llm:
        if not secrets.anthropic_api_key:
            print("ANTHROPIC_API_KEY is not set (use --fake-llm to test without it).", file=sys.stderr)
            return 2
        import anthropic

        client = anthropic.Anthropic(api_key=secrets.anthropic_api_key, max_retries=4)

    channels = [] if (args.dry_run or args.no_email) else make_channels(cfg, secrets)
    publisher = Publisher(cfg, secrets) if (cfg.publish.enabled and not args.dry_run) else None
    rng = random.Random(args.seed)
    res = run_episode(cfg, source=source, client=client, channels=channels, today=date.today(), rng=rng,
                      dry_run=args.dry_run, publisher=publisher)
    print(f"✅ {res.episode.title}\n   {res.out_dir / 'photostory.html'}")
    if res.link and not os.getenv("GITHUB_ACTIONS"):  # CI logs may be public — link goes by email only
        print(f"🔗 {res.link}")
    return 0


def cmd_render(args) -> int:
    """Render a finished episode (written by Claude in a chat, or by hand) from photo files."""
    import json as _json

    from .models import Episode, check_episode
    from .sources.local import _taken_at

    cfg = load_config(args.config)
    ep = Episode.model_validate(_json.loads(Path(args.episode).read_text()))
    files = [Path(f) for f in args.photos]
    dates = [d.strip() for d in args.dates.split(",")] if args.dates else []
    if dates and len(dates) != len(files):
        print("--dates needs one date per photo (YYYY-MM-DD, comma separated).", file=sys.stderr)
        return 2
    problems = check_episode(ep, len(files), len(ep.quiz))
    if problems:
        print("Episode problems:\n- " + "\n- ".join(problems), file=sys.stderr)
        return 1
    from datetime import datetime

    from .imaging import to_jpeg
    from .sources.base import Photo, PhotoRef

    photos = []
    for i, f in enumerate(files):
        taken = datetime.fromisoformat(dates[i]) if dates else _taken_at(f)
        jpeg, w, h = to_jpeg(f.read_bytes(), max_side=cfg.llm.image_max_side)
        photos.append(Photo(ref=PhotoRef(id=f.name, name=f.name, taken_at=taken), jpeg=jpeg, width=w, height=h))

    out = Path(args.out)
    family = args.family or cfg.story.family_name
    rendered = render_episode(ep, photos, date.today(), family, attached=True)
    write_outputs(rendered, photos, out)
    print(f"✅ {ep.title}\n   page: {out / 'photostory.html'}")
    if not args.no_pack:
        from .share import build_share_pack

        synth = None
        if not args.no_voice:
            from .voice import make_synth

            v = cfg.voices
            synth = make_synth(v.model_url, v.cache_dir, v.speaker_ids, v.length_scale)
        pack = build_share_pack(ep, photos, out / "whatsapp", video=not args.no_video,
                                chapter_seconds=cfg.whatsapp.chapter_seconds, synth=synth)
        print(f"   whatsapp: {len(pack.cards)} cards, polls.txt"
              + (f", video ({'talking' if pack.talking else 'silent'})" if pack.video else ""))
    return 0


def cmd_quotes(args) -> int:
    from .quotes import quotes_prompt

    print(quotes_prompt())
    return 0


def cmd_schema(args) -> int:
    import json as _json

    from .models import Episode

    print(_json.dumps(Episode.model_json_schema(), indent=1))
    return 0


def cmd_list(args) -> int:
    cfg = load_config(args.config)
    source = make_source(cfg, Secrets.from_env())
    _persist_rotated_token(source)
    refs = source.list_photos()
    usable = filter_refs(refs, cfg.source.exclude_patterns, cfg.source.min_side_px)
    print(f"{len(refs)} images found, {len(usable)} usable after filters.")
    for r in usable[:10]:
        print(f"  {r.taken_at.date() if r.taken_at else '????-??-??'}  {r.name}")
    return 0


def cmd_login(args) -> int:
    from .sources.onedrive import device_code_login

    client_id = args.client_id or os.getenv("MS_CLIENT_ID")
    if not client_id:
        print("Pass --client-id or set MS_CLIENT_ID.", file=sys.stderr)
        return 2
    tokens = device_code_login(client_id, tenant=args.tenant)
    Path(args.out).write_text(tokens["refresh_token"])
    os.chmod(args.out, 0o600)
    print(f"\n✅ Signed in. Refresh token saved to {args.out}.")
    print(f"   Store it as a GitHub secret:  gh secret set MS_REFRESH_TOKEN < {args.out}  — then delete the file.")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="photostory", description="Weekly family PhotoStory agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Pick photos, write the episode, send it")
    r.add_argument("--config", default="config.yaml")
    r.add_argument("--dry-run", action="store_true", help="Write files to out/ only; don't send or update history")
    r.add_argument("--no-email", action="store_true", help="Publish the page and print the link, but don't email")
    r.add_argument("--fake-llm", action="store_true", help="Use a canned episode instead of calling Claude")
    r.add_argument("--source-path", help="Use a local folder instead of the configured source")
    r.add_argument("--seed", type=int, default=None)
    r.set_defaults(fn=cmd_run)

    ls = sub.add_parser("list", help="Check the photo source and show what it finds")
    ls.add_argument("--config", default="config.yaml")
    ls.set_defaults(fn=cmd_list)

    rd = sub.add_parser("render", help="Render page + WhatsApp pack from an episode.json and photo files")
    rd.add_argument("--episode", required=True, help="Episode JSON (see `photostory schema`)")
    rd.add_argument("--photos", nargs="+", required=True, help="Photo files in episode order: photo 1, 2, …")
    rd.add_argument("--dates", help="Optional comma-separated YYYY-MM-DD per photo (else EXIF/mtime)")
    rd.add_argument("--out", default="out/render")
    rd.add_argument("--family")
    rd.add_argument("--config", default="config.yaml")
    rd.add_argument("--no-pack", action="store_true", help="Only the page, no WhatsApp cards/video")
    rd.add_argument("--no-video", action="store_true")
    rd.add_argument("--no-voice", action="store_true", help="Silent video (skip Piper TTS)")
    rd.set_defaults(fn=cmd_render)

    sub.add_parser("quotes", help="Print the curated collage quotes").set_defaults(fn=cmd_quotes)
    sub.add_parser("schema", help="Print the episode JSON schema").set_defaults(fn=cmd_schema)

    lg = sub.add_parser("onedrive-login", help="One-time Microsoft sign-in to get a refresh token")
    lg.add_argument("--client-id")
    lg.add_argument("--tenant", default="consumers")
    lg.add_argument("--out", default="onedrive.token")
    lg.set_defaults(fn=cmd_login)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
