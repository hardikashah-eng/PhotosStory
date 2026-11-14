"""Static checks for webapp/index.html (the full browser run lives in tests/webapp_e2e.py)."""
import json
import re
from pathlib import Path

PAGE = Path(__file__).resolve().parent.parent / "webapp" / "index.html"


def test_webapp_quotes_match_the_curated_list():
    from photostory.quotes import load_quotes

    html = PAGE.read_text()
    m = re.search(r"/\*QUOTES\*/(.*?);\n", html, re.S)
    page_quotes = {q[0]: (q[1], q[2]) for q in json.loads(m.group(1))}
    assert page_quotes == {q.id: (q.text, q.author) for q in load_quotes().values()}, "run python webapp/sync_quotes.py"


def test_webapp_pins_library_versions_and_has_no_secrets():
    html = PAGE.read_text()
    for lib in ["onnxruntime-web/1.18.0", "piper-wasm@1.0.0", "mp4-muxer@5.2.2"]:
        assert lib in html
    assert "sk-ant-" not in html.replace('placeholder="sk-ant-…"', "")
    assert "<title>Thursday PhotoStory</title>" in html
