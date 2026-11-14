import re
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import package_release  # noqa: E402


def test_skill_frontmatter_is_valid_for_claude():
    package_release.check_skill(ROOT / "skills" / "thursday-photostory")


def test_skill_mentions_every_cli_command_it_uses():
    text = (ROOT / "skills/thursday-photostory/SKILL.md").read_text()
    for cmd in ("photostory schema", "photostory quotes", "photostory render"):
        assert cmd in text


def test_check_skill_rejects_bad_metadata(tmp_path):
    d = tmp_path / "thursday-photostory"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: other-name\ndescription: x\n---\nbody")
    with pytest.raises(AssertionError, match="must match folder"):
        package_release.check_skill(d)
    (d / "SKILL.md").write_text("---\nname: thursday-photostory\ndescription: " + "x" * 201 + "\n---\n")
    with pytest.raises(AssertionError, match="1-200"):
        package_release.check_skill(d)


def test_zip_has_skill_folder_at_top_level(tmp_path):
    src = tmp_path / "s"
    (src / "assets").mkdir(parents=True)
    (src / "SKILL.md").write_text("x")
    (src / "assets" / "a.whl").write_text("y")
    package_release.zip_dir(src, tmp_path / "s.zip", "thursday-photostory")
    names = zipfile.ZipFile(tmp_path / "s.zip").namelist()
    assert names == ["thursday-photostory/SKILL.md", "thursday-photostory/assets/a.whl"]


def test_versions_agree():
    py = re.search(r'(?m)^version = "(.*)"$', (ROOT / "pyproject.toml").read_text()).group(1)
    import photostory

    assert photostory.__version__ == py
