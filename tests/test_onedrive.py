import httpx
import pytest

from photostory.sources.onedrive import GRAPH, OneDriveAuthError, OneDriveSource

from .conftest import jpeg_bytes


def make_transport(fail_custom_thumb=True, token_ok=True):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        seen.append(url)
        if "oauth2/v2.0/token" in url:
            if not token_ok:
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "expired"})
            return httpx.Response(200, json={"access_token": "AT", "refresh_token": "RT2"})
        assert req.headers["Authorization"] == "Bearer AT"
        if url.startswith(f"{GRAPH}/me/drive/special/cameraroll/children"):
            return httpx.Response(200, json={
                "value": [
                    {"id": "f1", "name": "2024", "folder": {"childCount": 2}},
                    {"id": "a", "name": "IMG_1.jpg", "file": {"mimeType": "image/jpeg"},
                     "photo": {"takenDateTime": "2024-07-04T10:00:00Z"}, "image": {"width": 4000, "height": 3000}},
                ],
                "@odata.nextLink": f"{GRAPH}/me/drive/special/cameraroll/children?page=2",
            }) if "page=2" not in url else httpx.Response(200, json={
                "value": [{"id": "v", "name": "clip.mp4", "file": {"mimeType": "video/mp4"}}]
            })
        if url.startswith(f"{GRAPH}/me/drive/items/f1/children"):
            return httpx.Response(200, json={"value": [
                {"id": "b", "name": "IMG_2.HEIC", "file": {"mimeType": "image/heic"}},
            ]})
        if "/thumbnails/0/c" in url and fail_custom_thumb:
            return httpx.Response(404)
        if "/thumbnails/0/" in url:
            return httpx.Response(200, content=jpeg_bytes(size=(800, 600)))
        return httpx.Response(404)

    return httpx.MockTransport(handler), seen


def test_lists_recursively_and_pages():
    transport, seen = make_transport()
    src = OneDriveSource("cid", "RT1", http=httpx.Client(transport=transport))
    refs = src.list_photos()
    assert {r.id for r in refs} == {"a", "b"}  # video skipped, subfolder walked
    a = next(r for r in refs if r.id == "a")
    assert a.taken_at.year == 2024 and a.width == 4000
    assert src.rotated_refresh_token == "RT2"
    assert any("page=2" in u for u in seen)


def test_fetch_falls_back_to_large_thumbnail():
    transport, seen = make_transport(fail_custom_thumb=True)
    src = OneDriveSource("cid", "RT1", http=httpx.Client(transport=transport))
    ref = src.list_photos()[0]
    photo = src.fetch(ref, 1024)
    assert photo.jpeg[:2] == b"\xff\xd8" and photo.width == 800
    assert any("/thumbnails/0/large/content" in u for u in seen)


def test_bad_refresh_token_is_explained():
    transport, _ = make_transport(token_ok=False)
    with pytest.raises(OneDriveAuthError, match="onedrive-login"):
        OneDriveSource("cid", "RT1", http=httpx.Client(transport=transport))


def test_folder_path_url():
    transport, seen = make_transport()
    src = OneDriveSource("cid", "RT1", path="Pictures/Family Trips", http=httpx.Client(transport=transport))
    assert src._root_children_url() == f"{GRAPH}/me/drive/root:/Pictures/Family%20Trips:/children"
