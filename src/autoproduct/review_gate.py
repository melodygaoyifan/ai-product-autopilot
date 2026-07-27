"""Fixture-registration gate for the six REVIEW voters (§11.19).

The product, profile, data, and upstream voters all register through
`product/voter_gate.py`; the review voters were the last roster riding
`bench` alone — a corpus-level recall/precision number, not a per-voter
registration decision. This closes that gap with the same standing
contract: 8 fixtures per voter (4 positive / 2 negative / 2 boundary),
≥87.5% to register, results in `.mas/voter-registry.yaml` under
`review/<voter>`, and the vote node fails closed on a voter whose latest
gate run FAILED.

Two things differ from the product gate, because review voters are a
different shape:

- The fixture artifact is a **unified diff**, and the gate runs the real
  `Voter` seat (`voters/base.py`) rather than re-prompting a charter body
  — the thing being registered is the seat as it actually votes, wrapper
  prompt and all.
- Review severities are `critical|high|medium|low`, so a negative fixture
  passes when the voter emits no critical/high finding on clean material
  (a medium nit on clean code is noise, not a registration failure).
"""

from __future__ import annotations

import pathlib

import yaml

from autoproduct.paths import skills_root
from autoproduct.product.voter_gate import (
    REGISTRATION_FLOOR,
    FixtureResult,
    GateRun,
    VoterFixture,
    VoterFixtureError,
)

REVIEW_STAGE = "review"
_REPO = pathlib.Path(__file__).resolve().parents[2]
REVIEW_FIXTURES = _REPO / "tests" / "integration" / "voters" / "fixtures" / REVIEW_STAGE
_BLOCKING_SEVERITIES = {"critical", "high"}


def review_voter_names(skills_dir: pathlib.Path | None = None) -> list[str]:
    """The six core review charters (profile deltas register per family)."""
    root = skills_dir or skills_root()
    return sorted(p.stem for p in root.glob("*.md"))


def load_review_fixtures(
    voter: str, root: pathlib.Path | None = None
) -> list[VoterFixture]:
    path = (root or REVIEW_FIXTURES) / f"{voter}.yaml"
    if not path.exists():
        raise VoterFixtureError(
            f"no fixture set at {path} — a voter without fixtures cannot "
            "register (§11.19)"
        )
    raw = yaml.safe_load(path.read_text()) or {}
    fixtures = [VoterFixture(**f) for f in raw.get("fixtures") or []]
    kinds = sorted(f.kind for f in fixtures)
    if (
        len(fixtures) != 8
        or kinds.count("positive") != 4
        or kinds.count("negative") != 2
        or kinds.count("boundary") != 2
    ):
        raise VoterFixtureError(
            f"review/{voter}: the standing contract is 8 fixtures "
            f"(4 positive, 2 negative, 2 boundary); got {len(fixtures)} ({kinds})"
        )
    return fixtures


def _judge(findings: list[dict], fixture: VoterFixture) -> FixtureResult:
    if fixture.should_find:
        for finding in findings:
            blob = " ".join(str(v) for v in finding.values()).lower()
            if all(term.lower() in blob for term in fixture.must_mention):
                return FixtureResult(
                    label=fixture.label, passed=True,
                    detail=f"found: {str(finding.get('title', ''))[:80]}",
                )
        return FixtureResult(
            label=fixture.label, passed=False,
            detail=f"no finding mentioned all of {fixture.must_mention} "
            f"({len(findings)} finding(s) emitted)",
        )
    blocking = [
        f for f in findings
        if str(f.get("severity", "")).lower() in _BLOCKING_SEVERITIES
    ]
    if blocking:
        return FixtureResult(
            label=fixture.label, passed=False,
            detail=f"{blocking[0].get('severity')} finding on clean material: "
            f"{str(blocking[0].get('title', ''))[:80]}",
        )
    return FixtureResult(
        label=fixture.label, passed=True, detail="no blocking finding on clean material"
    )


def run_review_voter_gate(
    voter_name: str,
    *,
    provider_override: str | None = None,
    skills_dir: pathlib.Path | None = None,
    fixtures_root: pathlib.Path | None = None,
    repo_dir: str = ".",
) -> GateRun:
    """Run one review voter against its 8 fixtures through the real seat."""
    from autoproduct.voters import load_voters

    fixtures = load_review_fixtures(voter_name, fixtures_root)
    root = skills_dir or skills_root()
    voters = [
        v for v in load_voters(root, provider_override=provider_override)
        if v.spec.name == voter_name
    ]
    if not voters:
        raise VoterFixtureError(f"no review charter named {voter_name!r} in {root}")
    voter = voters[0]

    results = []
    for fixture in fixtures:
        output = voter.run(fixture.artifact, context="", repo_dir=repo_dir)
        findings = [f.model_dump(mode="json") for f in output.findings]
        results.append(_judge(findings, fixture))
    passed = sum(1 for r in results if r.passed)
    rate = passed / len(fixtures)
    return GateRun(
        stage=REVIEW_STAGE, voter=voter_name, passed=passed, total=len(fixtures),
        rate=rate,
        status="registered" if rate >= REGISTRATION_FLOOR else "failed",
        results=results,
    )
