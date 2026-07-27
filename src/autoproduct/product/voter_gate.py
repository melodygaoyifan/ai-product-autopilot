"""The voter fixture gate (§11.19, applied to P-stage voters): 8 fixtures
per voter — 4 positive, 2 negative, 2 boundary — >=87.5% to register.

The gate runs against a REAL provider (`autoproduct voter-gate`), like the
review bench: judging an LLM voter takes an LLM. Results land in
`.mas/voter-registry.yaml`; the stage engine refuses a voter whose latest
gate run FAILED (fail closed on known-bad) and loads unregistered voters
with the fact recorded in the stage report — visible, never silent.

Scoring: a positive fixture passes when the voter emits >=1 finding
mentioning every `must_mention` term; a negative fixture passes when the
voter emits no MAJOR finding on clean material; boundary fixtures state
their own expectation.
"""

from __future__ import annotations

import pathlib

import yaml
from pydantic import BaseModel, Field

from autoproduct.providers import get_provider
from autoproduct.yamlx import extract_mapping

VOTER_REGISTRY_FILE = "voter-registry.yaml"
REGISTRATION_FLOOR = 0.875
from autoproduct.paths import skills_root

_REPO = pathlib.Path(__file__).resolve().parents[3]
_SKILLS = skills_root()  # charters ship in the package; fixtures stay repo-side
FIXTURES_ROOT = _REPO / "tests" / "integration" / "voters" / "fixtures" / "product"

# Voter families beyond the product stages (plan phase B): each maps to a
# skills subtree and a fixture subtree; the 8-fixture / 87.5% contract is
# identical for all of them.
FAMILY_SKILLS = {
    "web": _SKILLS / "profiles" / "web",
    "miniprogram": _SKILLS / "profiles" / "miniprogram",
    "app": _SKILLS / "profiles" / "app",
    "data": _SKILLS / "data",
    # Upstream critique rosters (doc 13 §25.1, plan phase D13): the
    # discover/plan/spec critics run through the same charter + fixture
    # registration contract as everything else.
    "discovery": _SKILLS / "upstream" / "discovery",
    "planning": _SKILLS / "upstream" / "planning",
    "spec": _SKILLS / "upstream" / "spec",
}
FAMILY_FIXTURES = {
    name: _REPO / "tests" / "integration" / "voters" / "fixtures" / name
    for name in FAMILY_SKILLS
}


def family_roots(stage: str):
    """(skills_root_for_charters, fixtures_root) for a stage or family."""
    if stage in FAMILY_SKILLS:
        return FAMILY_SKILLS[stage].parent, FAMILY_FIXTURES[stage].parent
    return None, None  # product stages use the defaults


class VoterFixture(BaseModel):
    label: str
    kind: str  # positive | negative | boundary
    should_find: bool
    must_mention: list[str] = Field(default_factory=list)
    artifact: str


class FixtureResult(BaseModel):
    label: str
    passed: bool
    detail: str


class GateRun(BaseModel):
    stage: str
    voter: str
    passed: int
    total: int
    rate: float
    status: str  # registered | failed
    results: list[FixtureResult]


class VoterFixtureError(RuntimeError):
    """A fixture set that violates the standing contract (8, 4/2/2 mix)."""


def load_voter_fixtures(
    stage: str, voter: str, root: pathlib.Path | None = None
) -> list[VoterFixture]:
    path = (root or FIXTURES_ROOT) / stage / f"{voter}.yaml"
    if not path.exists():
        raise VoterFixtureError(f"no fixture set at {path} — a voter without "
                                "fixtures cannot register (§11.19)")
    raw = yaml.safe_load(path.read_text()) or {}
    fixtures = [VoterFixture(**f) for f in raw.get("fixtures") or []]
    kinds = sorted(f.kind for f in fixtures)
    if len(fixtures) != 8 or kinds.count("positive") != 4 or kinds.count(
        "negative"
    ) != 2 or kinds.count("boundary") != 2:
        raise VoterFixtureError(
            f"{stage}/{voter}: the standing contract is 8 fixtures "
            f"(4 positive, 2 negative, 2 boundary); got {len(fixtures)} "
            f"({kinds})"
        )
    return fixtures


def _judge(findings: list[dict], fixture: VoterFixture) -> FixtureResult:
    if fixture.should_find:
        for finding in findings:
            blob = " ".join(str(v) for v in finding.values()).lower()
            if all(term.lower() in blob for term in fixture.must_mention):
                return FixtureResult(
                    label=fixture.label, passed=True,
                    detail=f"found: {finding.get('problem', '')[:80]}",
                )
        return FixtureResult(
            label=fixture.label, passed=False,
            detail=f"no finding mentioned all of {fixture.must_mention} "
            f"({len(findings)} finding(s) emitted)",
        )
    majors = [f for f in findings if f.get("severity") == "major"]
    if majors:
        return FixtureResult(
            label=fixture.label, passed=False,
            detail=f"major finding on clean material: {majors[0].get('problem', '')[:80]}",
        )
    return FixtureResult(label=fixture.label, passed=True, detail="quiet on clean material")


def run_voter_gate(
    stage: str,
    voter_name: str,
    voter_system: str,
    *,
    provider: str,
    voter_model: str = "claude-sonnet-5",
    fixtures_root: pathlib.Path | None = None,
) -> GateRun:
    fixtures = load_voter_fixtures(stage, voter_name, fixtures_root)
    provider_impl = get_provider(provider)
    results = []
    for fixture in fixtures:
        raw = provider_impl.complete(
            model=voter_model, system=voter_system, user=fixture.artifact,
            max_tokens=2048,
        )
        try:
            findings = [
                f for f in (extract_mapping(raw, ("findings",)).get("findings") or [])
                if isinstance(f, dict)
            ]
        except ValueError:
            findings = []
        results.append(_judge(findings, fixture))
    passed = sum(1 for r in results if r.passed)
    rate = passed / len(fixtures)
    return GateRun(
        stage=stage, voter=voter_name, passed=passed, total=len(fixtures),
        rate=rate,
        status="registered" if rate >= REGISTRATION_FLOOR else "failed",
        results=results,
    )


def record_gate_run(mas_dir: str | pathlib.Path, run: GateRun) -> pathlib.Path:
    path = pathlib.Path(mas_dir) / VOTER_REGISTRY_FILE
    registry = {}
    if path.exists():
        registry = yaml.safe_load(path.read_text()) or {}
    registry[f"{run.stage}/{run.voter}"] = {
        "status": run.status, "rate": round(run.rate, 3),
        "passed": run.passed, "total": run.total,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(registry, sort_keys=True))
    return path


def registry_status(mas_dir: str | pathlib.Path, stage: str, voter: str) -> str:
    """registered | failed | unregistered (no gate run recorded yet)."""
    path = pathlib.Path(mas_dir) / VOTER_REGISTRY_FILE
    if not path.exists():
        return "unregistered"
    registry = yaml.safe_load(path.read_text()) or {}
    entry = registry.get(f"{stage}/{voter}")
    return str(entry["status"]) if entry else "unregistered"
