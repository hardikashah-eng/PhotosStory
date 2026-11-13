from __future__ import annotations

from ..config import Config, Secrets
from .base import Photo, PhotoRef, PhotoSource
from .local import LocalSource
from .onedrive import OneDriveSource


def make_source(cfg: Config, secrets: Secrets) -> PhotoSource:
    s = cfg.source
    if s.type == "local":
        return LocalSource(s.path, max_depth=s.max_depth)
    return OneDriveSource(
        client_id=secrets.ms_client_id or "",
        refresh_token=secrets.ms_refresh_token or "",
        path=s.path,
        tenant=s.tenant,
        max_depth=s.max_depth,
        max_scan=s.max_scan,
    )


__all__ = ["Photo", "PhotoRef", "PhotoSource", "LocalSource", "OneDriveSource", "make_source"]
