import random
from datetime import date
from email import message_from_bytes, policy
from urllib.parse import parse_qs, unquote, urlparse

import boto3
import pytest
from botocore.config import Config as BotoConfig

from photostory.cli import run_episode
from photostory.config import Secrets
from photostory.deliver import EmailChannel
from photostory.publish import Publisher
from photostory.sources.local import LocalSource

from .test_pipeline import FakeSMTP


class FakeS3:
    def __init__(self, fail=False):
        self.objects, self.fail = {}, fail

    def put_object(self, Bucket, Key, Body, ContentType, CacheControl):
        if self.fail:
            raise ConnectionError("bucket unreachable")
        self.objects[Key] = (Body, ContentType)

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://signed.example/{Params['Key']}?X-Amz-Expires={ExpiresIn}"


def _run(cfg, publisher, rng_seed=0):
    FakeSMTP.sent.clear()
    secrets = Secrets(smtp_username="me@example.com", smtp_password="pw")
    ch = EmailChannel(cfg, secrets, smtp_factory=FakeSMTP)
    res = run_episode(cfg, source=LocalSource(cfg.source.path), client=None, channels=[ch],
                      today=date(2026, 11, 19), rng=random.Random(rng_seed), publisher=publisher)
    return res, message_from_bytes(FakeSMTP.sent[0].as_bytes(), policy=policy.default)


def test_public_link_mode_uploads_and_emails_link(cfg):
    cfg.publish.enabled = True
    s3 = FakeS3()
    pub = Publisher(cfg, Secrets(s3_bucket="b", publish_base_url="https://pub.example.dev/"), s3_client=s3)
    res, msg = _run(cfg, pub)

    page_key = next(k for k in s3.objects if k.endswith("index.html"))
    folder = page_key.rsplit("/", 1)[0]
    assert folder.startswith("episodes/2026-11-19-") and len(folder.split("-", 3)[-1]) >= 20  # unguessable
    body, ctype = s3.objects[page_key]
    assert ctype.startswith("text/html") and b"noindex" in body
    assert f'og:image" content="https://pub.example.dev/{folder}/cover.jpg"'.encode() in body
    assert res.link == f"https://pub.example.dev/{page_key}"

    # Email is short: link + WhatsApp share, one cover image, no attachment.
    assert "is ready" in msg["Subject"]
    parts = list(msg.walk())
    assert [p.get_content_type() for p in parts if p.get_content_maintype() == "image"] == ["image/jpeg"]
    assert not any(p.get_filename() == "photostory.html" for p in parts)
    html = msg.get_body(("html",)).get_content()
    assert res.link in html and "Unlisted link" in html
    wa = next(a for a in html.split('"') if a.startswith("https://wa.me/?text="))
    assert res.link in unquote(wa.split("=", 1)[1])


def test_presigned_mode_mentions_expiry(cfg):
    cfg.publish.enabled = True
    pub = Publisher(cfg, Secrets(s3_bucket="b"), s3_client=FakeS3())
    assert pub.mode == "presigned"
    res, msg = _run(cfg, pub)
    assert "X-Amz-Expires=604800" in res.link
    assert "expires on" in msg.get_body(("html",)).get_content()


def test_publish_failure_falls_back_to_full_email(cfg):
    cfg.publish.enabled = True
    pub = Publisher(cfg, Secrets(s3_bucket="b", publish_base_url="https://x"), s3_client=FakeS3(fail=True))
    res, msg = _run(cfg, pub)
    assert res.link is None
    assert any(p.get_filename() == "photostory.html" for p in msg.walk())


def test_real_boto3_presign_for_r2_works_offline(cfg):
    client = boto3.client("s3", endpoint_url="https://acct.r2.cloudflarestorage.com", region_name="auto",
                          aws_access_key_id="k", aws_secret_access_key="s", config=BotoConfig(signature_version="s3v4"))
    pub = Publisher(cfg, Secrets(s3_bucket="photostory"), s3_client=client)
    url = pub.plan(date(2026, 11, 19)).page_url
    q = parse_qs(urlparse(url).query)
    assert url.startswith("https://") and q["X-Amz-Expires"] == ["604800"] and "photostory" in url


def test_missing_bucket_is_clear(cfg):
    with pytest.raises(ValueError, match="bucket"):
        Publisher(cfg, Secrets(), s3_client=FakeS3())
