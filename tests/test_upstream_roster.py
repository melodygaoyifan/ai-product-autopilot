"""D13: the upstream critique rosters (doc 13 §25.1) — discover/plan/spec
critics as registered charter voters on the shared stage engine, the
single-panel prompts retired.
"""

from __future__ import annotations

import shutil

import pytest
import yaml

from ai_venture_studio.product.stage_engine import (
    load_voter_charters,
    run_critique_roster,
)
from ai_venture_studio.product.voter_gate import (
    FAMILY_FIXTURES,
    family_roots,
    load_voter_fixtures,
)
from ai_venture_studio.upstream import init_workspace

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)

ROSTERS = {
    "discovery": {"desirability", "feasibility", "viability",
                  "scope-discipline"},
    "planning": {"completeness", "dependency-realism", "risk-sequencing",
                 "parallelization-safety", "estimate-sanity"},
    "spec": {"testability", "consistency", "completeness", "ambiguity",
             "interface-impact"},
}


def test_rosters_match_doc_13_section_25_1():
    for stage, expected in ROSTERS.items():
        skills_root, _ = family_roots(stage)
        charters = {name for name, _ in load_voter_charters(stage, skills_root)}
        assert charters == expected, (stage, charters ^ expected)


@pytest.mark.parametrize(
    ("stage", "voter"),
    [(s, v) for s, roster in ROSTERS.items() for v in sorted(roster)],
)
def test_every_roster_voter_has_a_contract_fixture_set(stage, voter):
    _, fixtures_root = family_roots(stage)
    fixtures = load_voter_fixtures(stage, voter, fixtures_root)  # 8 / 4-2-2
    for fixture in fixtures:
        assert fixture.artifact.strip()
        if fixture.should_find:
            assert fixture.must_mention, f"{fixture.label}: positives name terms"


def test_fixture_files_match_charters_exactly():
    for stage, expected in ROSTERS.items():
        fixture_sets = {p.stem for p in FAMILY_FIXTURES[stage].glob("*.yaml")}
        assert fixture_sets == expected, (stage, fixture_sets ^ expected)


class _ScriptedRoster:
    """One targeted major from a single voter; verifier and leader by
    marker — exercises the voter → verify → leader path deterministically."""

    def complete(self, *, model, system, user, max_tokens=4096):
        from ai_venture_studio.product.stage_engine import (
            PRODUCT_LEADER_MARKER,
            PRODUCT_VERIFIER_MARKER,
            PRODUCT_VOTER_MARKER,
        )

        if PRODUCT_VERIFIER_MARKER in system:
            refute = "unverifiable-claim" in user
            return yaml.safe_dump({
                "verdict": "refuted" if refute else "verified",
                "reason": "scripted"})
        if PRODUCT_LEADER_MARKER in system:
            return yaml.safe_dump({"summary": "scripted leader summary"})
        if PRODUCT_VOTER_MARKER in system and "ScopeDiscipline" in system:
            return yaml.safe_dump({"findings": [
                {"severity": "major", "problem": "scope_never is empty",
                 "evidence": "scope_never: []"},
                {"severity": "major", "problem": "unverifiable-claim",
                 "evidence": "not in the artifact"},
            ]})
        if PRODUCT_VOTER_MARKER in system:
            return yaml.safe_dump({"findings": []})
        raise AssertionError(f"unexpected seat: {system[:60]}")


def test_roster_runs_voters_verify_and_leader(tmp_path):
    root = init_workspace(tmp_path / "p", "p", "web")
    skills_root, _ = family_roots("discovery")
    report = run_critique_roster(
        "discovery", "discovery",
        "scope_now: [a]\nscope_never: []\n", str(root),
        provider_impl=_ScriptedRoster(), skills_root=skills_root,
    )
    # The verified finding survives; the refuted plausible-but-wrong dies.
    assert [f.problem for f in report.voter_findings] == ["scope_never is empty"]
    assert report.voter_findings[0].voter == "scope-discipline"
    assert report.leader_summary == "scripted leader summary"
    assert set(report.unregistered_voters) == ROSTERS["discovery"]
    issues = report.as_issues()
    assert issues[0]["lens"] == "scope-discipline"
    assert issues[0]["severity"] == "major"


def test_roster_excludes_gate_failed_voters(tmp_path):
    root = init_workspace(tmp_path / "p", "p", "web")
    (root / ".mas" / "voter-registry.yaml").write_text(yaml.safe_dump({
        "discovery/scope-discipline": {"status": "failed", "rate": 0.5,
                                       "passed": 4, "total": 8},
        "discovery/desirability": {"status": "registered", "rate": 1.0,
                                   "passed": 8, "total": 8},
    }))
    skills_root, _ = family_roots("discovery")
    report = run_critique_roster(
        "discovery", "discovery",
        "scope_now: [a]\nscope_never: []\n", str(root),
        provider_impl=_ScriptedRoster(), skills_root=skills_root,
    )
    # §11.19: the failed voter's majors never reach the report.
    assert report.excluded_voters == ["scope-discipline"]
    assert report.voter_findings == []
    assert "desirability" not in report.unregistered_voters


def test_upstream_stages_carry_roster_lenses(tmp_path):
    """run_discovery on the mock provider routes critics through the
    charter roster: every issue's lens is a charter name, not the old
    panel's hardcoded lens vocabulary."""
    from ai_venture_studio.upstream import run_discovery

    root = init_workspace(tmp_path / "p", "p", "web")
    brief = run_discovery(root, "a link sharing tool", provider="mock")
    lenses = {i["lens"] for i in brief.critic_issues}
    assert lenses <= ROSTERS["discovery"]
    assert lenses  # the mock voter seat emits one nit per charter
