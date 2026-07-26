"""P0 opportunity sensing + P1 market tools (doc 20 §54-55, weeks P9-P12).

Clustering is deterministic near-dup (ADR-U05 ordering), the kill registry
surfaces history rather than vetoing, Gate PL0 checks well-formedness not
goodness, sizing refuses the invented TAM, and injection_scan treats the
retrieved corpus as adversarial by default.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from autoproduct.product import (
    DemandHypothesis,
    KillRegistryError,
    OpportunityCandidate,
    RawSignal,
    cluster_signals,
    gate_pl0,
    injection_scan,
    load_kill_registry,
    match_killed,
    sizing_calc,
)
from autoproduct.product.evidence import store_snapshot
from autoproduct.product.sizing import SizingFactor, TopDownCrosscheck

UPSTREAM = Path(__file__).parent / "fixtures" / "upstream"
TODAY = dt.date(2026, 7, 26)


# --- P0: clustering ----------------------------------------------------------


def test_near_duplicate_signals_cluster_and_distinct_ones_do_not():
    signals = [
        RawSignal(
            id="s1", source_id="support-tickets",
            text="Bulk export to CSV takes forever from the reports page, "
            "we do it every Friday",
        ),
        RawSignal(
            id="s2", source_id="support-tickets",
            text="Bulk export to CSV takes forever from the reports page, "
            "we do this every single Friday",
        ),
        RawSignal(
            id="s3", source_id="community",
            text="Would love a dark mode for late-night reviews",
        ),
    ]
    clusters = cluster_signals(signals)
    assert len(clusters) == 2
    assert {"s1", "s2"} in [set(c.signal_ids) for c in clusters]
    export_cluster = next(c for c in clusters if "s1" in c.signal_ids)
    # The representative is a real member, never a synthesized summary.
    assert export_cluster.representative in (signals[0].text, signals[1].text)


# --- kill registry read path (§20.54.3, §22.65.2) ------------------------------


def test_kill_registry_loads_matches_and_fails_loudly(tmp_path):
    assert load_kill_registry(tmp_path) == []
    (tmp_path / "kill-registry.yaml").write_text(
        "- id: PRD-2026-009\n"
        "  decided_at: '2026-06-20'\n"
        "  outcome: kill\n"
        "  reason: 'activation lift 2% vs 15% target; export-first onboarding "
        "does not motivate this segment'\n"
        "  statement: 'one-click bulk export onboarding for recruiting ops'\n"
        "  reusable_learning: 'the import path might work instead'\n"
        "  revisit_if: 'we acquire a segment with existing structured data'\n"
    )
    registry = load_kill_registry(tmp_path)
    matches = match_killed(
        "one-click bulk export onboarding for recruiting ops teams", registry
    )
    assert matches and matches[0].record.id == "PRD-2026-009"
    assert matches[0].record.revisit_if  # history travels with the match

    assert match_killed("realtime chat for gamers", registry) == []

    (tmp_path / "kill-registry.yaml").write_text("not: a-list\n")
    with pytest.raises(KillRegistryError, match="append-only"):
        load_kill_registry(tmp_path)


# --- Gate PL0 (§20.54.4) --------------------------------------------------------


def _candidate(cid: str, *, falsifier: str = "under 5% stub clicks in 2 weeks",
               test: str = "bulk-export stub behind a click counter") -> OpportunityCandidate:
    return OpportunityCandidate(
        id=cid,
        statement=f"Opportunity {cid}: reduce manual export pain",
        demand_hypothesis=DemandHypothesis(
            statement="admins will adopt one-click bulk export", falsifier=falsifier
        ),
        cheapest_test=test,
        claim_ledger={
            "claims": [
                {
                    "id": f"{cid}-C1",
                    "text": "Support tickets cluster on manual CSV export pain",
                    "kind": "user_need",
                    "source_type": "user_reported",
                    "n": 12,
                    "evidence": [
                        {
                            "method": "ticket_cluster",
                            "locator": "evidence://tickets/export-pain",
                            "retrieved_at": "2026-07-23T16:20:00Z",
                        }
                    ],
                    "falsifier": "cluster resolves to fewer than 5 distinct reporters",
                }
            ]
        },
        signal_refs=["s1", "s2"],
    )


def test_gate_pl0_passes_a_well_formed_set_and_surfaces_kills(tmp_path):
    (tmp_path / "kill-registry.yaml").write_text(
        "- {id: PRD-9, decided_at: '2026-06-20', outcome: kill,\n"
        "   reason: 'no adoption', statement: 'reduce manual export pain'}\n"
    )
    registry = load_kill_registry(tmp_path)
    candidates = [_candidate("cand-a"), _candidate("cand-b"), _candidate("cand-c")]
    result = gate_pl0(candidates, registry, today=TODAY)
    assert result.passed
    assert result.ranked_candidate_ids == ["cand-a", "cand-b", "cand-c"]
    assert candidates[0].killed_matches  # surfaced with history, not vetoed


def test_gate_pl0_blocks_thin_or_ill_formed_sets():
    result = gate_pl0([_candidate("only-one")], [], today=TODAY)
    assert not result.passed
    assert "insufficient_candidates" in {f.rule for f in result.findings}

    synthetic = _candidate("cand-x")
    synthetic.claim_ledger["claims"][0]["source_type"] = "model_inference"
    synthetic.claim_ledger["claims"][0]["evidence"] = []
    untestable = _candidate("cand-y", falsifier="  ")
    no_test = _candidate("cand-z", test="")
    result = gate_pl0([synthetic, untestable, no_test], [], today=TODAY)
    rules = {f.rule for f in result.findings}
    assert {"no_grounding_signal", "unfalsifiable_hypothesis", "no_cheapest_test"} <= rules


# --- sizing_calc fixture gate (§20.55.1) -----------------------------------------


def _sizing_fixtures():
    return yaml.safe_load((UPSTREAM / "sizing.yaml").read_text())["fixtures"]


@pytest.mark.parametrize("fixture", _sizing_fixtures(), ids=lambda f: f["label"])
def test_sizing_fixture(fixture):
    inp = fixture["input"]
    crosscheck = inp.get("top_down_crosscheck")
    result = sizing_calc(
        [SizingFactor(**f) for f in inp["factors"]],
        top_down_crosscheck=TopDownCrosscheck(**crosscheck) if crosscheck else None,
    )
    expect = fixture["expect"]
    assert result.status == expect["status"]
    assert {i.rule for i in result.issues} == set(expect["rules"])
    if expect["status"] == "ok":
        assert result.result_range is not None  # a range, never a point estimate
        low, high = result.result_range
        assert low <= result.midpoint <= high
    if expect.get("flagged") is not None:
        assert result.divergence.get("flagged") is expect["flagged"]
        assert result.divergence["note"].startswith("divergence recorded")


def test_sizing_fixture_gate_is_the_standing_eight():
    assert len(_sizing_fixtures()) == 8


# --- injection_scan fixture gate (§20.55.4, week P12) -----------------------------


def _injection_fixtures():
    return yaml.safe_load((UPSTREAM / "injection.yaml").read_text())["fixtures"]


def _materialize(fixture: dict, mas_dir) -> dict:
    """Store fixture snapshots for real so hashes are honest; then tamper
    or omit per the fixture's planted failure."""
    claims = []
    for claim in fixture["input"]["claims"]:
        evidence = []
        for entry in claim.get("evidence", []):
            record = {"locator": entry["locator"], "retrieved_at": "2026-07-20T09:00:00Z"}
            if entry.get("missing"):
                record["artifact_hash"] = "sha256:" + "0" * 64
            elif "snapshot" in entry:
                snap = store_snapshot(entry["snapshot"].encode(), mas_dir, suffix=".txt")
                record["artifact_hash"] = snap.artifact_hash
                if entry.get("drift"):
                    Path(snap.path).write_bytes(b"silently changed after retrieval")
            evidence.append(record)
        claims.append({"id": claim["id"], "evidence": evidence})
    return {"claims": claims}


@pytest.mark.parametrize("fixture", _injection_fixtures(), ids=lambda f: f["label"])
def test_injection_fixture(fixture, tmp_path):
    ledger = _materialize(fixture, tmp_path)
    findings = injection_scan(ledger, tmp_path)
    assert {f.rule for f in findings} == set(fixture["expect"]["rules"])


def test_injection_fixture_gate_is_the_standing_eight():
    assert len(_injection_fixtures()) == 8
