"""v0.35.0: the review voters get the registration gate every other roster
already had (§11.19), plus per-project policy thresholds and the
next_tasks marker fix."""

from __future__ import annotations

import pytest
import yaml

from ai_venture_studio.paths import skills_root
from ai_venture_studio.product.voter_gate import (
    VoterFixtureError,
    record_gate_run,
    registry_status,
)
from ai_venture_studio.review_gate import (
    REVIEW_FIXTURES,
    REVIEW_STAGE,
    load_review_fixtures,
    review_voter_names,
    run_review_voter_gate,
)

EXPECTED_VOTERS = {
    "context", "correctness", "performance", "repo_graph", "security", "style",
}


def test_charter_fixture_bijection():
    assert set(review_voter_names()) == EXPECTED_VOTERS
    fixture_sets = {p.stem for p in REVIEW_FIXTURES.glob("*.yaml")}
    assert fixture_sets == EXPECTED_VOTERS


@pytest.mark.parametrize("voter", sorted(EXPECTED_VOTERS))
def test_fixture_set_meets_the_standing_contract(voter):
    fixtures = load_review_fixtures(voter)  # raises on 8 / 4-2-2 breach
    assert len(fixtures) == 8
    for fixture in fixtures:
        assert fixture.artifact.strip().startswith("diff --git"), fixture.label
        if fixture.should_find:
            assert fixture.must_mention, f"{fixture.label}: a positive names its terms"


def test_contract_violations_fail_loudly(tmp_path):
    (tmp_path / "security.yaml").write_text(yaml.safe_dump({
        "fixtures": [{"label": "only-one", "kind": "positive", "should_find": True,
                      "must_mention": ["x"], "artifact": "diff --git a/a b/a"}]
    }))
    with pytest.raises(VoterFixtureError, match="standing contract"):
        load_review_fixtures("security", tmp_path)
    with pytest.raises(VoterFixtureError, match="cannot register"):
        load_review_fixtures("no-such-voter", tmp_path)


def test_gate_scores_a_real_seat_and_records_the_run(tmp_path):
    """The mock provider finds exactly the planted patterns, so a fixture
    set built from them registers and one built from clean diffs does not —
    the scoring path, end to end, through the real Voter seat."""
    root = tmp_path / "fx"
    root.mkdir()
    planted = (
        "diff --git a/app/x.py b/app/x.py\n--- a/app/x.py\n+++ b/app/x.py\n"
        "@@ -1,1 +1,1 @@\n+    q = f\"SELECT * FROM t WHERE a = '{a}'\"\n"
    )
    clean = (
        "diff --git a/app/x.py b/app/x.py\n--- a/app/x.py\n+++ b/app/x.py\n"
        "@@ -1,1 +1,1 @@\n+    return 1\n"
    )
    good = [
        {"label": f"pos-{i}", "kind": "positive", "should_find": True,
         "must_mention": ["sql"], "artifact": planted} for i in range(4)
    ] + [
        {"label": f"neg-{i}", "kind": "negative", "should_find": False,
         "artifact": clean} for i in range(2)
    ] + [
        {"label": "bound-quiet", "kind": "boundary", "should_find": False,
         "artifact": clean},
        {"label": "bound-find", "kind": "boundary", "should_find": True,
         "must_mention": ["sql"], "artifact": planted},
    ]
    (root / "security.yaml").write_text(yaml.safe_dump({"fixtures": good}))
    run = run_review_voter_gate(
        "security", provider_override="mock", fixtures_root=root,
        repo_dir=str(tmp_path),
    )
    assert run.status == "registered" and run.passed == 8
    assert run.stage == REVIEW_STAGE

    mas = tmp_path / ".mas"
    record_gate_run(mas, run)
    assert registry_status(mas, REVIEW_STAGE, "security") == "registered"
    assert registry_status(mas, REVIEW_STAGE, "style") == "unregistered"

    # A voter that misses its own positives fails: same fixtures, terms the
    # mock never emits.
    missing = [dict(f, must_mention=["quantum-tunnelling"])
               if f.get("should_find") else f for f in good]
    (root / "security.yaml").write_text(yaml.safe_dump({"fixtures": missing}))
    run = run_review_voter_gate(
        "security", provider_override="mock", fixtures_root=root,
        repo_dir=str(tmp_path),
    )
    assert run.status == "failed" and run.passed == 3  # the 3 non-finding cases
    record_gate_run(mas, run)
    assert registry_status(mas, REVIEW_STAGE, "security") == "failed"


def test_unknown_charter_name_is_an_error(tmp_path):
    root = tmp_path / "fx"
    root.mkdir()
    (root / "ghost.yaml").write_text(yaml.safe_dump({"fixtures": [
        {"label": f"f{i}", "kind": k, "should_find": False, "artifact": "diff --git a/a b/a"}
        for i, k in enumerate(["positive"] * 4 + ["negative"] * 2 + ["boundary"] * 2)
    ]}))
    with pytest.raises(VoterFixtureError, match="no review charter"):
        run_review_voter_gate("ghost", provider_override="mock", fixtures_root=root,
                              repo_dir=str(tmp_path))


def test_skills_root_holds_exactly_the_six_core_charters():
    """Profile/data/product charters live in subdirectories; the six core
    review seats are the top-level .md files."""
    assert {p.stem for p in skills_root().glob("*.md")} == EXPECTED_VOTERS


# --- fail-closed wiring in the vote node -------------------------------------


def _diff() -> str:
    return (
        "diff --git a/app/x.py b/app/x.py\n--- a/app/x.py\n+++ b/app/x.py\n"
        "@@ -1,1 +1,1 @@\n+    return 1\n"
    )


def _vote(tmp_path, registry: dict):
    from ai_venture_studio.orchestrator.graph import vote_node

    mas = tmp_path / ".mas"
    mas.mkdir(exist_ok=True)
    (mas / "voter-registry.yaml").write_text(yaml.safe_dump(registry))
    return vote_node(
        {"diff": {"raw": _diff()}, "mode": "standard"},
        skills_dir=str(skills_root()), provider_override="mock",
        repo_dir=str(tmp_path),
    )


def test_failed_review_voter_does_not_vote(tmp_path):
    update = _vote(tmp_path, {
        f"{REVIEW_STAGE}/security": {"status": "failed", "rate": 0.5,
                                     "passed": 4, "total": 8},
        f"{REVIEW_STAGE}/style": {"status": "registered", "rate": 1.0,
                                  "passed": 8, "total": 8},
    })
    assert update["excluded_voters"] == ["security"]
    assert "security" not in {o["voter"] for o in update["voter_outputs"]}
    assert "style" not in update["unregistered_voters"]  # it registered
    assert "correctness" in update["unregistered_voters"]  # no run recorded


def test_no_registry_means_every_voter_votes_but_is_reported(tmp_path):
    update = _vote(tmp_path, {})
    assert update["excluded_voters"] == []
    assert set(update["unregistered_voters"]) == EXPECTED_VOTERS
    assert {o["voter"] for o in update["voter_outputs"]} == EXPECTED_VOTERS


def test_every_voter_failing_refuses_to_review(tmp_path):
    with pytest.raises(RuntimeError, match="refusing to review"):
        _vote(tmp_path, {
            f"{REVIEW_STAGE}/{name}": {"status": "failed", "rate": 0.0,
                                       "passed": 0, "total": 8}
            for name in EXPECTED_VOTERS
        })
