"""End-to-end check of webapp/index.html in headless Chrome.

CDN libraries and the voice model are served from local copies, and the Claude API is
faked with a canned episode, so this runs offline. Usage:

  python tests/webapp_e2e.py --libs /path/to/node_modules --voice /path/to/voice.onnx \
      --episode episode.json --photos a.jpg b.jpg ... --out outdir [--writer api|offline]
"""
from __future__ import annotations

import argparse
import base64
import functools
import http.server
import json
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

WEBAPP = Path(__file__).resolve().parent.parent / "webapp"


def serve(directory: Path) -> int:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--libs", type=Path, required=True)
    ap.add_argument("--voice", type=Path)
    ap.add_argument("--episode", type=Path)
    ap.add_argument("--photos", nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--writer", default="api")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    port = serve(WEBAPP)
    nm = a.libs
    routes = {
        "https://cdnjs.cloudflare.com/ajax/libs/onnxruntime-web/1.18.0/": nm / "onnxruntime-web/dist/",
        "https://cdn.jsdelivr.net/npm/@diffusionstudio/piper-wasm@1.0.0/build/": nm / "@diffusionstudio/piper-wasm/build/",
        "https://cdn.jsdelivr.net/npm/mp4-muxer@5.2.2/build/": nm / "mp4-muxer/build/",
    }
    calls = {"api": 0}

    def handle(route):
        url = route.request.url
        if url.startswith("https://api.anthropic.com/"):
            calls["api"] += 1
            body = {"content": [{"type": "text", "text": a.episode.read_text()}]}
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(body),
                                 headers={"access-control-allow-origin": "*"})
        if url.startswith("https://huggingface.co/") and a.voice:
            f = Path(str(a.voice) + ".json") if url.endswith(".json") else a.voice
            return route.fulfill(status=200, body=f.read_bytes(), headers={"access-control-allow-origin": "*"})
        for prefix, local in routes.items():
            if url.startswith(prefix):
                f = local / url[len(prefix):].split("?")[0]
                if f.exists():
                    ct = "application/wasm" if f.suffix == ".wasm" else "text/javascript" if f.suffix in (".js", ".mjs") else "application/octet-stream"
                    return route.fulfill(status=200, body=f.read_bytes(), content_type=ct, headers={"access-control-allow-origin": "*"})
                return route.fulfill(status=404)
        if url.startswith("https://fonts."):
            return route.continue_() if False else route.fulfill(status=200, body="", content_type="text/css")
        return route.continue_()

    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=a.chrome, args=["--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": 412, "height": 900}, device_scale_factor=2)
        ctx.route("**/*", handle)
        pg = ctx.new_page()
        logs = []
        pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        pg.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))
        pg.goto(f"http://127.0.0.1:{port}/index.html")
        pg.screenshot(path=str(a.out / "0_start.png"))
        pg.set_input_files("#files", a.photos)
        pg.wait_for_function("document.getElementById('count').textContent.includes('chosen')", timeout=60000)
        pg.check(f"input[name=writer][value={a.writer}]")
        if a.writer == "api":
            pg.fill("#apikey", "sk-ant-test")
        if not a.voice:
            pg.uncheck("#wantVoice")
        pg.screenshot(path=str(a.out / "1_picked.png"), full_page=True)
        pg.click("#make")
        pg.wait_for_function("[...document.querySelectorAll('#status div')].some(d => /Done!|✕|err/.test(d.className + d.textContent) && (d.className==='done' && d.textContent.startsWith('Done') || d.className==='err' && !d.textContent.includes('voice') && !d.textContent.includes('video')))", timeout=600000)
        status = pg.eval_on_selector_all("#status div", "els => els.map(e => e.className + ': ' + e.textContent)")
        info = pg.evaluate("""async () => {
            const b64 = async (blob) => { const u = new Uint8Array(await blob.arrayBuffer()); let s=''; for (let i=0;i<u.length;i+=0x8000) s += String.fromCharCode.apply(null, u.subarray(i,i+0x8000)); return btoa(s); };
            return { cards: S.cards.length, video: S.video ? await b64(S.video.blob) : null, talking: S.video?.talking, codec: S.video?.audioCodec,
                     collage: await b64(await new Promise(r => S.collage.toBlob(r, 'image/jpeg', .9))),
                     card3: await b64(await new Promise(r => S.cards[3].toBlob(r, 'image/jpeg', .9))),
                     title: S.ep.title, clips: (S.clips||[]).filter(Boolean).length,
                     years: chosen().map(p => p.taken && p.taken.getFullYear()) };
        }""")
        for name in ("video", "collage", "card3"):
            if info.get(name):
                ext = "mp4" if name == "video" else "jpg"
                (a.out / f"{name}.{ext}").write_bytes(base64.b64decode(info.pop(name)))
        pg.screenshot(path=str(a.out / "2_story.png"))
        pg.click("#tabs button[data-p=p-share]")
        pg.screenshot(path=str(a.out / "3_share.png"), full_page=True)
        b.close()
    print(json.dumps({"status": status, "api_calls": calls["api"], **info}, indent=1))
    errors = [l for l in logs if "PAGEERROR" in l]
    print("\n".join(errors)[:3000])
    ok = any(x.startswith("done: Done!") for x in status) and not errors
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
