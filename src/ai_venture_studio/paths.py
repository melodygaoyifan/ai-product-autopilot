"""Package-anchored resource roots.

Runtime resources ship INSIDE the package so an installed wheel behaves like
a git checkout. Repo-root-relative paths (`parents[N] / "profiles"`) resolve
to `site-packages/../../profiles` once installed — which does not exist — so
`avs init --profile web` failed for every pip user with "available: []" while
working perfectly in a checkout. v0.54.1 swept the whole class.

The repo keeps root symlinks (`profiles`, `blocks`, `editions`, `skills`) so
humans and docs can use the familiar paths. Code resolves through here.

Development-only data (`benchmarks/`, `tests/`) is deliberately NOT shipped —
a wheel should not carry a benchmark corpus — so `repo_data()` returns None
when absent and callers say so plainly instead of failing with an empty list.
"""

from __future__ import annotations

import pathlib


def package_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent


def skills_root() -> pathlib.Path:
    return package_root() / "skills"


def profiles_root() -> pathlib.Path:
    """Domain profiles (web / miniprogram / app / game / data)."""
    return package_root() / "profiles"


def blocks_root() -> pathlib.Path:
    """Pre-reviewed code blocks copied verbatim into generated products."""
    return package_root() / "blocks"


def editions_root() -> pathlib.Path:
    """Edition presets and the offline demo bundle.

    Packaged as `edition_data/` rather than `editions/` because
    `editions.py` is a module in the same package and the two names would
    collide.
    """
    return package_root() / "edition_data"


def repo_data(*parts: str) -> pathlib.Path | None:
    """A path under the source checkout, or None when running from a wheel.

    For resources that are development-only by design: the benchmark corpora
    and the test fixture sets. Returning None lets a command explain that it
    needs a checkout, instead of reporting an empty corpus as a result.
    """
    candidate = package_root().parents[1].joinpath(*parts)
    return candidate if candidate.exists() else None
