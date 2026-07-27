"""Package-anchored resource roots.

The voter charters ship INSIDE the package (src/autoproduct/skills/) so an
installed wheel behaves like a git checkout — repo-root-relative paths broke
every stage command for pip users. The repo keeps a root `skills` symlink
for humans and docs; code resolves through here, never through parents[N].
"""

from __future__ import annotations

import pathlib


def skills_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / "skills"
