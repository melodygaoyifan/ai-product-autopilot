"""The live operator-side records (P20 remainder): the attention log,
the first Gate PL5 evaluation, and the launch experiment's power verdict —
each mechanically consistent with the machinery it claims to have run.
"""

from __future__ import annotations

import pathlib

import yaml

from autoproduct.evidence.cohort import required_n_two_proportions
from autoproduct.experiment.design import verify_at_analysis

REPO = pathlib.Path(__file__).resolve().parents[1]


def _load(rel: str) -> dict:
    return yaml.safe_load((REPO / rel).read_text())


def test_experiment_run_pin_still_verifies():
    """The run record's claim 'pin verified' must be re-derivable — a
    drifted design voids the analysis, not just the assertion."""
    run = _load("launch/experiment-run.yaml")["run"]
    text = (REPO / "launch" / "experiment.yaml").read_text()
    verify_at_analysis(text, run["preregistration_hash"])  # raises on drift
    assert run["preregistration_verified"] is True


def test_experiment_run_power_numbers_are_rederivable():
    run = _load("launch/experiment-run.yaml")["run"]
    design = _load("launch/experiment.yaml")["experiment"]["power"]
    n = required_n_two_proportions(
        design["baseline"], design["mde_relative"],
        alpha=design["alpha"], power=design["power"],
    )
    assert run["power_check"]["required_n_per_arm"] == n
    assert run["power_check"]["required_n_total"] == 2 * n
    available = run["power_check"]["available_traffic"]["unique_visitors_14d"]
    # The verdict must match the arithmetic, whichever way it points.
    blocked = run["power_check"]["verdict"] == "BLOCKED(INSUFFICIENT_POWER)"
    assert blocked == (available < 2 * n)


def test_experiment_run_evidence_is_typed():
    run = _load("launch/experiment-run.yaml")["run"]
    evidence = run["power_check"]["available_traffic"]["evidence"]
    for key in ("method", "locator", "retrieved_at"):
        assert str(evidence.get(key, "")).strip(), key
    fallback = run["qualitative_fallback"]
    assert fallback["asked"] == len(fallback["answers"])  # n recorded, not inferred


def test_attention_log_rows_are_honest():
    rows = _load("metrics/attention-log.yaml")["log"]
    assert rows, "the log exists to be written"
    for row in rows:
        assert row["status"] in {"logged", "not_tracked"}
        if row["status"] == "not_tracked":
            # A week that was not tracked carries no number — logged,
            # never estimated (metrics/weekly_maintenance_attention.md).
            assert row["hours"] is None
        else:
            assert isinstance(row["hours"], (int, float)) and row["hours"] >= 0
        assert str(row.get("week", "")).strip()


def test_pl5_evaluation_is_consistent_with_the_log():
    evaluation = _load("launch/gate-pl5-evaluation.yaml")["evaluation"]
    rows = _load("metrics/attention-log.yaml")["log"]
    breaches = [r for r in rows
                if r["status"] == "logged" and (r["hours"] or 0) > 4.0]
    # The recorded fired-list must match what the log can support: with
    # fewer than 4 consecutive logged breaches, nothing may claim to fire.
    if len(breaches) < 4:
        assert evaluation["fired"] == []
    assert evaluation["requires_human_decision"] == bool(
        evaluation["fired"] or evaluation["loop_budget_exhausted"]
    )
    assert evaluation["loop_index"] <= evaluation["max_loops"]
