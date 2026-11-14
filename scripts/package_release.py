"""Build the downloadable release assets into dist/:

- thursday-photostory-skill.zip   Claude skill (upload in Claude: Customize → Skills → + → Upload a skill).
                                   Top level is the skill folder, with the engine wheel in assets/.
- photostory-webapp.zip            The phone web app, to self-host anywhere (or open locally).
- photostory-<version>-py3-none-any.whl / .tar.gz   The Python engine (pip install).

Usage: python scripts/package_release.py [--version 0.2.0]
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = "thursday-photostory"


def set_version(version: str) -> None:
    py = ROOT / "pyproject.toml"
    py.write_text(re.sub(r'(?m)^version = ".*"$', f'version = "{version}"', py.read_text(), count=1))
    init = ROOT / "photostory/__init__.py"
    init.write_text(re.sub(r'__version__ = ".*"', f'__version__ = "{version}"', init.read_text()))


def check_skill(skill_dir: Path) -> None:
    text = (skill_dir / "SKILL.md").read_text()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md needs YAML frontmatter"
    meta = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    name, desc = meta.get("name", "").strip(), meta.get("description", "").strip()
    assert name == skill_dir.name, f"name '{name}' must match folder '{skill_dir.name}'"
    assert re.fullmatch(r"[a-z0-9-]{1,64}", name), "name: lowercase letters, numbers, hyphens"
    assert 0 < len(desc) <= 200, f"description must be 1-200 characters (is {len(desc)})"


def zip_dir(src: Path, dest: Path, arc_root: str) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f"{arc_root}/{f.relative_to(src)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version")
    ap.add_argument("--out", default=str(ROOT / "dist"))
    a = ap.parse_args()
    out = Path(a.out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    if a.version:
        set_version(a.version.lstrip("v"))

    # 1) Python engine
    subprocess.run([sys.executable, "-m", "build", "--outdir", str(out), str(ROOT)], check=True)
    wheel = next(out.glob("photostory-*.whl"))

    # 2) Skill zip: <skill>/SKILL.md + assets/<wheel>
    stage = out / "_skill" / SKILL
    shutil.copytree(ROOT / "skills" / SKILL, stage)
    (stage / "assets").mkdir(exist_ok=True)
    shutil.copy(wheel, stage / "assets" / wheel.name)
    check_skill(stage)
    skill_zip = out / f"{SKILL}-skill.zip"
    zip_dir(stage, skill_zip, SKILL)
    shutil.rmtree(out / "_skill")

    # 3) Web app zip
    web_zip = out / "photostory-webapp.zip"
    zip_dir(ROOT / "webapp", web_zip, "photostory-webapp")

    for f in sorted(out.iterdir()):
        print(f"{f.stat().st_size / 1e6:6.2f} MB  {f.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
