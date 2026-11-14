import json
import random
from datetime import date
from email import message_from_bytes, policy
from pathlib import Path

from photostory.cli import run_episode
from photostory.config import Secrets
from photostory.deliver import EmailChannel
from photostory.sources.local import LocalSource


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, u, p):
        assert u and p

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def test_local_source_skips_non_images(photo_dir):
    refs = LocalSource(photo_dir).list_photos()
    assert len(refs) == 13  # 12 photos + screenshot; notes.txt ignored
    assert any("summer" in r.id for r in refs)


def test_dry_run_writes_outputs_without_sending(cfg):
    res = run_episode(cfg, source=LocalSource(cfg.source.path), client=None, channels=[], today=date(2026, 11, 12),
                          rng=random.Random(0), dry_run=True)
    ep, out = res.episode, res.out_dir
    for f in ["photostory.html", "email.html", "episode.md", "episode.json"]:
        assert (out / f).exists()
    page = (out / "photostory.html").read_text()
    assert page.count("data:image/jpeg;base64,") == 10
    assert "Screenshot" not in (out / "photos.json").read_text()
    assert not Path(cfg.history_file).exists()  # dry run leaves history alone


def test_full_run_sends_email_and_records_history(cfg):
    FakeSMTP.sent.clear()
    secrets = Secrets(smtp_username="me@example.com", smtp_password="pw")
    ch = EmailChannel(cfg, secrets, smtp_factory=FakeSMTP)
    res = run_episode(cfg, source=LocalSource(cfg.source.path), client=None, channels=[ch],
                          today=date(2026, 11, 12), rng=random.Random(0))
    ep = res.episode
    assert len(FakeSMTP.sent) == 1
    msg = message_from_bytes(FakeSMTP.sent[0].as_bytes(), policy=policy.default)
    assert ep.title in msg["Subject"]
    parts = list(msg.walk())
    images = [p for p in parts if p.get_content_type() == "image/jpeg"]
    assert len(images) == 10 and all(p["Content-ID"] for p in images)
    html = next(p for p in parts if p.get_content_type() == "text/html" and not p.get_filename()).get_payload(decode=True).decode()
    for p in images:
        assert "cid:" + p["Content-ID"].strip("<>") in html
    assert any(p.get_filename() == "photostory.html" for p in parts)

    hist = json.loads(Path(cfg.history_file).read_text())
    assert len(hist["episodes"]) == 1 and len(hist["episodes"][0]["photos"]) == 10

    # Next week: a fresh set (only 12 photos, so at least 2 new ones and no crash)
    run_episode(cfg, source=LocalSource(cfg.source.path), client=None, channels=[ch],
                         today=date(2026, 11, 19), rng=random.Random(1))
    hist = json.loads(Path(cfg.history_file).read_text())
    assert set(hist["episodes"][0]["photos"]) != set(hist["episodes"][1]["photos"])


def test_html_is_escaped(cfg):
    from photostory.generator import fake_episode
    from photostory.render import render_episode

    from .conftest import make_photos

    photos = make_photos(3)
    ep = fake_episode(photos, cfg)
    ep.title = "<script>alert(1)</script>"
    r = render_episode(ep, photos, date(2026, 11, 12), "Fam")
    assert "<script>alert(1)" not in r.page_html and "<script>alert(1)" not in r.email_html


def test_render_command_from_episode_json(tmp_path, photo_dir):
    from photostory.cli import main
    from photostory.config import Config
    from photostory.generator import fake_episode

    from .conftest import make_photos

    ep = fake_episode(make_photos(3), Config())
    (tmp_path / "ep.json").write_text(ep.model_dump_json())
    files = sorted(str(p) for p in photo_dir.glob("IMG_*.jpg"))[:3]
    rc = main(["render", "--episode", str(tmp_path / "ep.json"), "--photos", *files, "--dates", "2009-10-18,2012-05-27,2026-01-10",
               "--out", str(tmp_path / "out"), "--no-pack"])
    assert rc == 0 and (tmp_path / "out" / "photostory.html").exists()
    rc = main(["render", "--episode", str(tmp_path / "ep.json"), "--photos", *files[:2], "--out", str(tmp_path / "o2"), "--no-pack"])
    assert rc == 1  # 3-photo episode with only 2 photos is rejected


def test_quotes_and_schema_commands(capsys):
    from photostory.cli import main

    assert main(["quotes"]) == 0 and "Emerson" in capsys.readouterr().out
    assert main(["schema"]) == 0 and '"voices"' in capsys.readouterr().out
