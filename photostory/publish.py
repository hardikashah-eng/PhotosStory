"""Publish the weekly page to S3-compatible storage and return a shareable link.

Works with Cloudflare R2 (recommended, free tier), AWS S3, Backblaze B2, MinIO...

Two link modes:
- "public":    https://<public_base_url>/episodes/<date>-<random>/index.html
               The bucket is publicly readable but every episode lives under a
               128-bit random folder name, so it can't be guessed or listed
               (same model as a Google Photos "anyone with the link" share).
- "presigned": a signed URL that expires after link_expiry_days (max 7).
               Nothing in the bucket is public at all.

The link is only ever sent by email — never logged in CI (logs of public repos are public).
"""

from __future__ import annotations

import secrets as pysecrets
from dataclasses import dataclass
from datetime import date
from typing import Any

from .config import Config, Secrets

MAX_PRESIGN_SECONDS = 7 * 24 * 3600  # SigV4 limit


@dataclass
class PublishPlan:
    page_key: str
    cover_key: str
    page_url: str
    cover_url: str


class Publisher:
    def __init__(self, cfg: Config, secrets: Secrets, s3_client: Any | None = None):
        p = cfg.publish
        self.bucket = secrets.s3_bucket or p.bucket
        self.public_base_url = (secrets.publish_base_url or p.public_base_url or "").rstrip("/")
        self.prefix = p.prefix.strip("/")
        self.expiry = min(p.link_expiry_days * 24 * 3600, MAX_PRESIGN_SECONDS)
        if not self.bucket:
            raise ValueError("publish is enabled but no bucket is configured (publish.bucket or S3_BUCKET).")
        if s3_client is None:
            import boto3
            from botocore.config import Config as BotoConfig

            if not (secrets.s3_access_key_id and secrets.s3_secret_access_key):
                raise ValueError("S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY must be set to publish.")
            s3_client = boto3.client(
                "s3",
                endpoint_url=secrets.s3_endpoint_url or p.endpoint_url,
                aws_access_key_id=secrets.s3_access_key_id,
                aws_secret_access_key=secrets.s3_secret_access_key,
                region_name=p.region,
                config=BotoConfig(signature_version="s3v4"),
            )
        self.s3 = s3_client

    @property
    def mode(self) -> str:
        return "public" if self.public_base_url else "presigned"

    def _url(self, key: str) -> str:
        if self.public_base_url:
            return f"{self.public_base_url}/{key}"
        return self.s3.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=self.expiry
        )

    def plan(self, episode_date: date) -> PublishPlan:
        folder = f"{self.prefix}/{episode_date.isoformat()}-{pysecrets.token_urlsafe(16)}"
        page_key, cover_key = f"{folder}/index.html", f"{folder}/cover.jpg"
        return PublishPlan(page_key, cover_key, self._url(page_key), self._url(cover_key))

    def upload(self, plan: PublishPlan, page_html: str, cover_jpeg: bytes) -> None:
        common = {"Bucket": self.bucket, "CacheControl": "private, max-age=3600"}
        self.s3.put_object(Key=plan.cover_key, Body=cover_jpeg, ContentType="image/jpeg", **common)
        self.s3.put_object(Key=plan.page_key, Body=page_html.encode(), ContentType="text/html; charset=utf-8", **common)
