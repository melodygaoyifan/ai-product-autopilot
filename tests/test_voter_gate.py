"""The voter fixture-registration gate (§11.19 for P-stage voters) and the
strategy loader — the two gaps closed after the cross-validation audit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from autoproduct.product.stage_engine import load_voter_charters, run_product_stage
from autoproduct.product.stages import opportunity_spec
from autoproduct.product.strategy import StrategyError, load_strategy
from autoproduct.product.voter_gate import (
    FIXTURES_ROOT,
    VoterFixtureError,
    load_voter_fixtures,
    record_gate_run,
    registry_status,
    run_voter_gate,
)

STAGES = {
    "opportunity": 5, "market": 6, "prd": 5, "evidence": 5, "prioritization": 3,
}


def _all_voters():
    return [
        pytest.param(stage, path.stem, id=f"{stage}/{path.stem}")
        for stage in STAGES
        for path in sorted((FIXTURES_ROOT / stage).glob("*.yaml"))
    ]


def test_every_charter_has_a_fixture_set_and_vice_versa():
    for stage, expected in STAGES.items():
        charters = {name for name, _ in load_voter_charters(stage)}
        fixture_sets = {p.stem for p in (FIXTURES_ROOT / stage).glob("*.yaml")}
        assert charters == fixture_sets, (stage, charters ^ fixture_sets)
        assert len(charters) == expected


@pytest.mark.parametrize(("stage", "voter"), _all_voters())
def test_fixture_set_meets_the_standing_contract(stage, voter):
    fixtures = load_voter_fixtures(stage, voter)  # raises on 8 / 4-2-2 breach
    for fixture in fixtures:
        assert fixture.artifact.strip()
        if fixture.should_find:
            assert fixture.must_mention, f"{fixture.label}: a positive names its terms"


def test_contract_violations_fail_loudly(tmp_path):
    (tmp_path / "opportunity").mkdir()
    (tmp_path / "opportunity" / "novelty.yaml").write_text(yaml.safe_dump({
        "fixtures": [{"label": "only-one", "kind": "positive",
                      "should_find": True, "must_mention": ["x"], "artifact": "a"}]
    }))
    with pytest.raises(VoterFixtureError, match="standing contract"):
        load_voter_fixtures("opportunity", "novelty", tmp_path)
    with pytest.raises(VoterFixtureError, match="cannot register"):
        load_voter_fixtures("opportunity", "no-such-voter", tmp_path)


# --- scoring, threshold, registry --------------------------------------------


def _mini_fixture_root(tmp_path: Path) -> Path:
    fixtures = []
    for i in range(4):
        fixtures.append({"label": f"pos-{i}", "kind": "positive", "should_find": True,
                         "must_mention": ["planted-alpha"],
                         "artifact": f"PLANTED case {i}: the value drifted."})
    for i in range(2):
        fixtures.append({"label": f"neg-{i}", "kind": "negative", "should_find": False,
                         "artifact": f"clean case {i}, nothing wrong here."})
    fixtures.append({"label": "bound-quiet", "kind": "boundary", "should_find": False,
                     "artifact": "borderline but fine."})
    fixtures.append({"label": "bound-find", "kind": "boundary", "should_find": True,
                     "must_mention": ["planted-alpha"],
                     "artifact": "PLANTED subtle case."})
    root = tmp_path / "fixtures"
    (root / "opportunity").mkdir(parents=True)
    (root / "opportunity" / "probe.yaml").write_text(
        yaml.safe_dump({"fixtures": fixtures})
    )
    return root


class _SharpVoter:
    """Finds the plant iff it is there — a voter that deserves to register."""

    def complete(self, *, model, system, user, max_tokens=4096):
        if "PLANTED" in user:
            return yaml.safe_dump({"findings": [
                {"severity": "major", "problem": "planted-alpha detected",
                 "evidence": user[:40]}]})
        return yaml.safe_dump({"findings": []})


class _NoisyVoter:
    """Flags everything — fails negatives, and its positives miss the terms."""

    def complete(self, *, model, system, user, max_tokens=4096):
        return yaml.safe_dump({"findings": [
            {"severity": "major", "problem": "something feels off",
             "evidence": user[:40]}]})


def test_gate_registers_sharp_and_fails_noisy(tmp_path, monkeypatch):
    root = _mini_fixture_root(tmp_path)
    import autoproduct.product.voter_gate as vg

    monkeypatch.setattr(vg, "get_provider", lambda name: _SharpVoter())
    run = run_voter_gate("opportunity", "probe", "system", provider="x",
                         fixtures_root=root)
    assert run.status == "registered" and run.passed == 8

    monkeypatch.setattr(vg, "get_provider", lambda name: _NoisyVoter())
    run = run_voter_gate("opportunity", "probe", "system", provider="x",
                         fixtures_root=root)
    assert run.status == "failed"
    assert run.passed == 0  # positives miss the terms, negatives get majors

    mas = tmp_path / ".mas"
    record_gate_run(mas, run)
    assert registry_status(mas, "opportunity", "probe") == "failed"
    assert registry_status(mas, "opportunity", "other") == "unregistered"


def test_engine_refuses_failed_voters_and_reports_unregistered(tmp_path):
    ws = tmp_path
    mas = ws / ".mas"
    mas.mkdir()
    (mas / "signal-sources.yaml").write_text(
        "- id: support-tickets\n  standing: first-party, ours\n"
        "  match: ['evidence://']\n"
    )
    (mas / "voter-registry.yaml").write_text(yaml.safe_dump({
        "opportunity/novelty": {"status": "failed", "rate": 0.5,
                                "passed": 4, "total": 8},
        "opportunity/fit": {"status": "registered", "rate": 1.0,
                            "passed": 8, "total": 8},
    }))
    report = run_product_stage(
        opportunity_spec(str(ws)), "clusters: []", str(ws), provider="mock"
    )
    assert report.excluded_voters == ["novelty"]
    assert "novelty" not in {f.voter for f in report.voter_findings}
    assert set(report.unregistered_voters) == {
        "signal_strength", "falsifiability", "duplication"
    }


# --- strategy.yaml (§20.54.3) --------------------------------------------------


def test_strategy_loads_and_reaches_the_fit_voter_context(tmp_path):
    mas = tmp_path / ".mas"
    mas.mkdir()
    (mas / "signal-sources.yaml").write_text(
        "- id: support-tickets\n  standing: first-party, ours\n"
        "  match: ['evidence://']\n"
    )
    assert load_strategy(mas).constraints == []  # absent file: no constraints

    (mas / "strategy.yaml").write_text(yaml.safe_dump({
        "product": "build pipeline for solo founders",
        "constraints": ["no realtime collaboration infrastructure this year"],
    }))
    strategy = load_strategy(mas)
    assert strategy.constraints[0].startswith("no realtime")

    spec = opportunity_spec(str(tmp_path))
    context = spec.voter_context(object(), "candidates: []")
    assert "no realtime collaboration" in context

    (mas / "strategy.yaml").write_text("not: [a: mapping")
    with pytest.raises(StrategyError):
        load_strategy(mas)
