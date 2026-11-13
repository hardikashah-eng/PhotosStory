"""OneDrive photos via Microsoft Graph.

Auth model: a public-client app registration + a long-lived refresh token
(obtained once with `photostory onedrive-login`, device-code flow). Every run
exchanges the refresh token for an access token. Microsoft rotates refresh
tokens, so the newest one is exposed as `OneDriveSource.rotated_refresh_token`
for the caller to persist (the GitHub workflow writes it back to the repo secret).

Scope is read-only: Files.Read offline_access.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from urllib.parse import quote

import httpx

from ..imaging import to_jpeg
from .base import Photo, PhotoRef

GRAPH = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com"
SCOPES = "Files.Read offline_access"
_SELECT = "id,name,file,folder,photo,image,size"


class OneDriveAuthError(RuntimeError):
    pass


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def refresh_access_token(
    client: httpx.Client, client_id: str, refresh_token: str, tenant: str = "consumers"
) -> tuple[str, str]:
    """Exchange a refresh token. Returns (access_token, new_refresh_token)."""
    resp = client.post(
        f"{LOGIN}/{tenant}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": SCOPES,
        },
    )
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code != 200 or "access_token" not in body:
        raise OneDriveAuthError(
            f"Token refresh failed ({resp.status_code}): {body.get('error')}: "
            f"{(body.get('error_description') or '')[:200]} — re-run `photostory onedrive-login`."
        )
    return body["access_token"], body.get("refresh_token", refresh_token)


def device_code_login(client_id: str, tenant: str = "consumers", client: httpx.Client | None = None) -> dict:
    """Interactive one-time login. Prints a code to enter at microsoft.com/devicelogin."""
    client = client or httpx.Client(timeout=30)
    r = client.post(f"{LOGIN}/{tenant}/oauth2/v2.0/devicecode", data={"client_id": client_id, "scope": SCOPES})
    r.raise_for_status()
    flow = r.json()
    print(flow["message"], flush=True)
    interval = int(flow.get("interval", 5))
    deadline = time.time() + int(flow.get("expires_in", 900))
    while time.time() < deadline:
        time.sleep(interval)
        t = client.post(
            f"{LOGIN}/{tenant}/oauth2/v2.0/token",
            data={
                "client_id": client_id,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": flow["device_code"],
            },
        ).json()
        if "access_token" in t:
            return t
        err = t.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        raise OneDriveAuthError(f"Login failed: {err}: {t.get('error_description', '')[:200]}")
    raise OneDriveAuthError("Login timed out.")


class OneDriveSource:
    def __init__(
        self,
        client_id: str,
        refresh_token: str,
        path: str = "special:cameraroll",
        tenant: str = "consumers",
        max_depth: int = 4,
        max_scan: int = 20000,
        http: httpx.Client | None = None,
    ):
        if not client_id or not refresh_token:
            raise OneDriveAuthError("MS_CLIENT_ID and MS_REFRESH_TOKEN must be set for the OneDrive source.")
        self.http = http or httpx.Client(timeout=60, follow_redirects=True)
        self.path = path.strip().strip("/")
        self.max_depth = max_depth
        self.max_scan = max_scan
        access, self.rotated_refresh_token = refresh_access_token(self.http, client_id, refresh_token, tenant)
        self._headers = {"Authorization": f"Bearer {access}"}

    # ---- Graph helpers -------------------------------------------------
    def _get(self, url: str, **kw) -> httpx.Response:
        for attempt in range(4):
            r = self.http.get(url, headers=self._headers, **kw)
            if r.status_code in (429, 503, 504):
                time.sleep(int(r.headers.get("Retry-After", 2 ** attempt)))
                continue
            return r
        return r

    def _root_children_url(self) -> str:
        if self.path.startswith("special:"):
            return f"{GRAPH}/me/drive/special/{self.path.split(':', 1)[1]}/children"
        if not self.path:
            return f"{GRAPH}/me/drive/root/children"
        return f"{GRAPH}/me/drive/root:/{quote(self.path)}:/children"

    # ---- PhotoSource ---------------------------------------------------
    def list_photos(self) -> list[PhotoRef]:
        refs: list[PhotoRef] = []
        queue: deque[tuple[str, int]] = deque([(self._root_children_url(), 0)])
        while queue and len(refs) < self.max_scan:
            url, depth = queue.popleft()
            params: dict | None = {"$select": _SELECT, "$top": "200"}
            while url and len(refs) < self.max_scan:
                r = self._get(url, params=params)
                if r.status_code == 404:
                    raise FileNotFoundError(f"OneDrive folder not found: {self.path!r}")
                r.raise_for_status()
                body = r.json()
                for item in body.get("value", []):
                    if "folder" in item:
                        if depth < self.max_depth:
                            queue.append((f"{GRAPH}/me/drive/items/{item['id']}/children", depth + 1))
                        continue
                    mime = (item.get("file") or {}).get("mimeType", "")
                    if not mime.startswith("image/"):
                        continue  # skip videos, docs, etc.
                    image = item.get("image") or {}
                    refs.append(
                        PhotoRef(
                            id=item["id"],
                            name=item.get("name", ""),
                            taken_at=_parse_dt((item.get("photo") or {}).get("takenDateTime")),
                            width=image.get("width"),
                            height=image.get("height"),
                        )
                    )
                url, params = body.get("@odata.nextLink"), None  # nextLink already carries the query
        return refs

    def fetch(self, ref: PhotoRef, max_side: int) -> Photo:
        # Server-side thumbnails are JPEG even for HEIC originals and much smaller
        # to download; fall back to the original file if a size isn't available.
        candidates = [
            f"{GRAPH}/me/drive/items/{ref.id}/thumbnails/0/c{max_side}x{max_side}/content",
            f"{GRAPH}/me/drive/items/{ref.id}/thumbnails/0/large/content",
            f"{GRAPH}/me/drive/items/{ref.id}/content",
        ]
        last_err = None
        for url in candidates:
            r = self._get(url)
            if r.status_code == 200 and r.content:
                try:
                    jpeg, w, h = to_jpeg(r.content, max_side=max_side)
                    return Photo(ref=ref, jpeg=jpeg, width=w, height=h)
                except Exception as e:  # e.g. HEIC original without pillow-heif
                    last_err = e
                    continue
            last_err = f"HTTP {r.status_code}"
        raise RuntimeError(f"Could not download {ref.name}: {last_err}")
