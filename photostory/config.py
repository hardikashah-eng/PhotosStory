"""Configuration: a YAML file for behaviour, environment variables for secrets.

Secrets are never read from the YAML file so the config can be committed safely.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    type: Literal["onedrive", "local"] = "onedrive"
    # OneDrive: a drive path like "Pictures/Family", or a special folder such as
    # "special:cameraroll" / "special:photos". Local: a folder on disk.
    path: str = "special:cameraroll"
    tenant: str = "consumers"  # "consumers" for personal OneDrive, "common"/tenant id for work
    max_depth: int = 4
    max_scan: int = 20000
    exclude_patterns: list[str] = Field(default_factory=lambda: ["screenshot", "screen shot", "screen_shot"])
    min_side_px: int = 500


class StoryConfig(BaseModel):
    photo_count: int = Field(default=10, ge=3, le=20)
    family_name: str = "Our Family"
    # Optional cast the story may use, e.g. ["Dad, the snack detective", "Mia, age 9, loves dragons"].
    characters: list[str] = Field(default_factory=list)
    audience: str = "the whole family, kids included"
    language: str = "English"
    quiz_questions: int = Field(default=5, ge=3, le=10)
    avoid_repeat_days: int = 180
    # Optional rotating themes; one is picked per episode. Empty = model's choice.
    themes: list[str] = Field(
        default_factory=lambda: [
            "a secret mission",
            "a time-travel mix-up",
            "a nature documentary narrated by a very dramatic owl",
            "a cooking show where everything goes slightly wrong",
            "a pirate treasure hunt",
            "a superhero origin story",
            "a mystery: who ate the last cookie?",
            "a space expedition",
        ]
    )


class LLMConfig(BaseModel):
    model: str = "claude-sonnet-5-5"
    max_tokens: int = 8000
    temperature: float | None = None  # None = model default
    image_max_side: int = 1024


class EmailConfig(BaseModel):
    enabled: bool = True
    to: list[str] = Field(default_factory=list)  # overridden by EMAIL_TO env (comma separated)
    from_addr: str | None = None  # defaults to SMTP_USERNAME
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    subject_prefix: str = "📸 Thursday PhotoStory"
    attach_interactive_page: bool = True


class PublishConfig(BaseModel):
    """Host the weekly page and send a link instead of the full content."""

    enabled: bool = False
    bucket: str | None = None  # or S3_BUCKET secret
    endpoint_url: str | None = None  # or S3_ENDPOINT_URL secret, e.g. https://<account>.r2.cloudflarestorage.com
    region: str = "auto"  # "auto" for R2; e.g. "us-west-2" for AWS
    # Set (or PUBLISH_BASE_URL secret) for permanent unguessable links, e.g. https://pub-xxxx.r2.dev
    # Leave empty for signed links that expire after link_expiry_days.
    public_base_url: str | None = None
    prefix: str = "episodes"
    link_expiry_days: int = Field(default=7, ge=1, le=7)


class WhatsAppConfig(BaseModel):
    """Story cards, quiz polls and a short video that play natively in WhatsApp."""

    enabled: bool = True
    video: bool = True
    chapter_seconds: float = Field(default=5.0, ge=2, le=12)
    attach_to_email: bool = True
    max_attachment_mb: float = 20.0  # stay under common mail limits (Gmail: 25 MB)


class VoicesConfig(BaseModel):
    """Talking photos: each photo 'says' a line, spoken in the video (Piper TTS) and on the page."""

    enabled: bool = True
    model_url: str = "https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-libritts-high.tar.gz"
    cache_dir: str = "~/.cache/photostory/voices"
    speaker_ids: list[int] = Field(default_factory=lambda: [0, 14, 30, 61, 102, 150, 211, 340, 466, 580, 712, 860])
    length_scale: float = Field(default=1.0, ge=0.6, le=1.6)  # >1 = slower speech


class Config(BaseModel):
    source: SourceConfig = SourceConfig()
    story: StoryConfig = StoryConfig()
    llm: LLMConfig = LLMConfig()
    email: EmailConfig = EmailConfig()
    publish: PublishConfig = PublishConfig()
    whatsapp: WhatsAppConfig = WhatsAppConfig()
    voices: VoicesConfig = VoicesConfig()
    history_file: str = "state/history.json"
    output_dir: str = "out"


class Secrets(BaseModel):
    anthropic_api_key: str | None = None
    ms_client_id: str | None = None
    ms_refresh_token: str | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    publish_base_url: str | None = None

    @classmethod
    def from_env(cls) -> "Secrets":
        env = lambda k: os.getenv(k) or None  # noqa: E731 — treat empty CI secrets as unset
        return cls(
            anthropic_api_key=env("ANTHROPIC_API_KEY"),
            ms_client_id=env("MS_CLIENT_ID"),
            ms_refresh_token=env("MS_REFRESH_TOKEN"),
            smtp_username=env("SMTP_USERNAME"),
            smtp_password=env("SMTP_PASSWORD"),
            s3_access_key_id=env("S3_ACCESS_KEY_ID"),
            s3_secret_access_key=env("S3_SECRET_ACCESS_KEY"),
            s3_endpoint_url=env("S3_ENDPOINT_URL"),
            s3_bucket=env("S3_BUCKET"),
            publish_base_url=env("PUBLISH_BASE_URL"),
        )


def load_config(path: str | Path | None) -> Config:
    data: dict = {}
    if path and Path(path).exists():
        data = yaml.safe_load(Path(path).read_text()) or {}
    cfg = Config.model_validate(data)

    # Env overrides that keep personal details out of a (possibly public) repo.
    if to := os.getenv("EMAIL_TO"):
        cfg.email.to = [a.strip() for a in to.split(",") if a.strip()]
    if fam := os.getenv("PHOTOSTORY_FAMILY_NAME"):
        cfg.story.family_name = fam
    if chars := os.getenv("PHOTOSTORY_CHARACTERS"):
        cfg.story.characters = [c.strip() for c in chars.split(";") if c.strip()]
    if src := os.getenv("PHOTOSTORY_SOURCE_PATH"):
        cfg.source.path = src
    return cfg
