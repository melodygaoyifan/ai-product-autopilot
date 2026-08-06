"""`__version__` drifted from pyproject for two releases (v0.71.0 and
v0.71.1 both shipped declaring 0.70.1) because nothing compared them. The
release checklist said to bump both; a checklist is a habit, and this repo's
own thesis is that habits lapse. This is the check that does not."""

import pathlib
import re
import tomllib

import ai_venture_studio

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_dunder_version_matches_pyproject():
    assert ai_venture_studio.__version__ == _pyproject_version(), (
        "src/ai_venture_studio/__init__.py __version__ and pyproject.toml "
        "version disagree — bump both."
    )


def test_changelog_leads_with_the_version_being_shipped():
    """The top entry must be the version in pyproject, so a release cannot go
    out describing itself as the previous one."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## v(\d+\.\d+\.\d+)", text, flags=re.MULTILINE)
    assert headings, "CHANGELOG.md has no '## vX.Y.Z' entries"
    assert headings[0] == _pyproject_version(), (
        f"CHANGELOG's newest entry is v{headings[0]} but pyproject says "
        f"{_pyproject_version()}"
    )
