"""Copy photostory/data/quotes.yaml into webapp/index.html (single source of truth for quotes)."""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def quotes_js() -> str:
    q = yaml.safe_load((ROOT / "photostory/data/quotes.yaml").read_text())["quotes"]
    return json.dumps([[x["id"], x["text"], x["author"], x.get("source", ""), x.get("tags", [])] for x in q], ensure_ascii=False)


def sync() -> bool:
    page = ROOT / "webapp/index.html"
    html = page.read_text()
    new = re.sub(r"/\*QUOTES\*/.*?(;\n)", lambda m: "/*QUOTES*/" + quotes_js() + m.group(1), html, count=1, flags=re.S)
    if new != html:
        page.write_text(new)
    return new != html


if __name__ == "__main__":
    print("updated" if sync() else "already in sync")
