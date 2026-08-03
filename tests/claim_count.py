"""PC-1 self-measurement: does the claimed test count match the real one?

`test_editions_platform.py` enforces the ledger against OVERclaiming — every
number in the README has to resolve to a claim, and `claim_lint` has to pass.
Nothing measured the suite itself, so an UNDERstated PC-1 stayed green
indefinitely: it sat at 1572 while the suite really passed 1655, through
several commits and a release. A claim nobody can falsify mechanically is
exactly what this repo says it does not ship (ADR-U29).

PC-1's own wording is "at the current **tag**", so this is enforced where
that sentence becomes a published number — the release run, which sets
`AVS_RELEASE_CHECK`. On an ordinary full run a mismatch is reported loudly
instead, because main drifting between releases is normal and failing every
test-adding commit would be a workflow tax rather than a safety property.
"""

from __future__ import annotations

from pathlib import Path

LEDGER = Path(__file__).parent.parent / "claims" / "platform.yaml"
RELEASE_ENV = "AVS_RELEASE_CHECK"


def claimed_test_count(ledger_path: Path | None = None) -> int | None:
    """PC-1's `n`, or None when the ledger has no such claim.

    Read with the project's own tolerant YAML path so a ledger the rest of the
    suite can parse is never unreadable here.
    """
    import yaml

    path = Path(ledger_path) if ledger_path else LEDGER
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    for claim in data.get("claims") or []:
        if isinstance(claim, dict) and claim.get("id") == "PC-1":
            n = claim.get("n")
            return int(n) if isinstance(n, int) else None
    return None


def is_whole_suite_run(args, keyword: str, markexpr: str, rootdir) -> bool:
    """True only for an unfiltered run of everything.

    Measured, not guessed: a bare `uv run pytest` arrives with
    `args == [<rootdir>]`, while `pytest tests/test_x.py` names the file. A
    subset would compare its own handful against the whole suite's claim and
    fail for no reason — and subsets are what everyone runs all day.
    """
    if keyword or markexpr:
        return False
    root = str(rootdir)
    return list(args) in ([], [root], [root + "/"], ["."])


def verdict(passed: int, claimed: int | None) -> str | None:
    """None when the claim holds; otherwise the sentence to show a human."""
    if claimed is None:
        return (
            "PC-1 is missing from claims/platform.yaml — the suite count is "
            f"{passed} and nothing claims it."
        )
    if passed == claimed:
        return None
    direction = "understates" if claimed < passed else "overstates"
    return (
        f"PC-1 {direction} the suite: it claims {claimed} passing tests, the "
        f"run passed {passed}. Re-measure — set `n:` and the `text:` count in "
        "claims/platform.yaml, and the count in the README's prose — or the "
        "released number is fiction. (This is the check that was missing when "
        "PC-1 sat at 1572 while the suite passed 1655.)"
    )
