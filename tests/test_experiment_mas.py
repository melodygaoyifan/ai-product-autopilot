"""The experiment MAS deterministic layer (§21.61, ADR-U24) — and the
v2.5.0 gate proofs: one pre-registered two-stage experiment run to
completion; a post-hoc edit blocked by the hash pin; an underpowered
design returning BLOCKED(INSUFFICIENT_POWER) with the required n stated.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ai_venture_studio.experiment import (
    ArmReading,
    CompoundingBoundaryError,
    EthicsVerdict,
    GuardrailReading,
    IllegalStopError,
    PreregistrationError,
    admit_to_compounding,
    benjamini_hochberg,
    declare_stop,
    gate_pl3_exp,
    load_design,
    lock_preregistration,
    obrien_fleming_boundaries,
    peek,
    power_calc,
    run_two_stage,
    verify_at_analysis,
)

FIXTURES = Path(__file__).parent / "fixtures" / "experiment"


def _fixtures():
    return yaml.safe_load((FIXTURES / "design_checks.yaml").read_text())["fixtures"]


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda f: f["label"])
def test_design_check_fixture(fixture):
    inp, expect = fixture["input"], fixture["expect"]
    design_yaml = yaml.safe_dump({"experiment": inp["design"]})
    if "schema_error" in expect:
        with pytest.raises(ValueError, match=expect["schema_error"]):
            load_design(design_yaml)
        return
    design = load_design(design_yaml)
    power_result = power_calc(
        baseline=design.power.baseline,
        mde_relative=design.power.mde_relative,
        arms=design.design_stage1.arms,
        weekly_traffic=inp["power_context"]["weekly_traffic"],
        max_days=inp["power_context"]["max_days"],
    )
    result = gate_pl3_exp(
        design,
        power_result,
        arms_instrumented=True,
        ethics=EthicsVerdict(
            veto="ethics_veto" in inp, grounds=inp.get("ethics_veto", "")
        ),
    )
    assert result.passed is expect["gate_passed"], result.findings
    for needle in expect["findings_contain"]:
        assert any(needle in f for f in result.findings), (needle, result.findings)


def test_design_fixture_gate_is_the_standing_eight():
    assert len(_fixtures()) == 8


def test_ethics_veto_is_alone_and_unweighed():
    fixture = next(f for f in _fixtures() if f["label"] == "ethics-veto-stops-everything")
    design = load_design(yaml.safe_dump({"experiment": fixture["input"]["design"]}))
    power_result = power_calc(
        baseline=0.062, mde_relative=0.15, arms=6, weekly_traffic=20000, max_days=60
    )
    result = gate_pl3_exp(
        design, power_result, arms_instrumented=False,  # would also fail…
        ethics=EthicsVerdict(veto=True, grounds="resetting countdown"),
    )
    assert len(result.findings) == 1  # …but the veto is not weighed among findings
    assert result.findings[0].startswith("ETHICS VETO")


# --- Benjamini-Hochberg ---------------------------------------------------------


def test_benjamini_hochberg_known_examples():
    results = benjamini_hochberg([0.001, 0.04, 0.2], q=0.05)
    assert [r.significant for r in results] == [True, False, False]
    all_pass = benjamini_hochberg([0.01, 0.02, 0.03, 0.04, 0.05], q=0.05)
    assert all(r.significant for r in all_pass)  # classic step-up property
    assert benjamini_hochberg([], q=0.05) == []


# --- sequential monitoring -------------------------------------------------------


def test_obrien_fleming_boundaries_are_conservative_early():
    bounds = obrien_fleming_boundaries(4, alpha=0.05)
    assert bounds == sorted(bounds, reverse=True)  # strictly harder early
    assert bounds[0] == pytest.approx(3.9199, abs=1e-3)
    assert bounds[-1] == pytest.approx(1.9600, abs=1e-3)  # nominal at horizon

    early_null = peek(2.0, 1, bounds)  # would be "significant" fixed-horizon!
    assert early_null.action == "continue"
    with pytest.raises(IllegalStopError, match="no other stop is legal"):
        declare_stop(early_null)

    crossed = peek(4.1, 1, bounds)
    assert crossed.action == "stop_efficacy"
    declare_stop(crossed)  # legal

    with pytest.raises(IllegalStopError, match="schedule"):
        peek(2.0, 5, bounds)


# --- pre-registration lock (invariant 14.17) ---------------------------------------


DESIGN_YAML = """\
experiment:
  id: EXP-2026-031
  hypothesis: "Outcome-led headline raises signup-start rate"
  primary_metric: signup_start_rate
  guardrail_metrics: [unsubscribe_rate]
  design:
    stage1: {arms: 3, correction: benjamini_hochberg, q: 0.10}
    stage2: {arms: 2, fresh_sample: true}
  power: {baseline: 0.06, mde_relative: 0.5, alpha: 0.05, power: 0.80}
  monitoring: {method: sequential, spending: obrien_fleming, peeks: 4}
  stopping_rule: "Horizon or boundary. No other stop is legal."
  decision_rule: "Adopt only if stage2 primary significant and guardrails hold."
  preregistration_hash: ""
"""


def test_preregistration_pin_survives_its_own_insertion_and_blocks_edits():
    pin = lock_preregistration(DESIGN_YAML)
    pinned_yaml = DESIGN_YAML.replace(
        'preregistration_hash: ""', f"preregistration_hash: {pin}"
    )
    verify_at_analysis(pinned_yaml, pin)  # writing the pin in changes nothing

    edited = pinned_yaml.replace(
        "guardrail_metrics: [unsubscribe_rate]",
        "guardrail_metrics: []",  # the classic post-hoc edit: drop the guardrail
    )
    with pytest.raises(PreregistrationError, match="edited after exposure"):
        verify_at_analysis(edited, pin)


# --- the v2.5.0 proof: one pre-registered two-stage experiment, run to completion --


def _pinned_design():
    pin = lock_preregistration(DESIGN_YAML)
    pinned_yaml = DESIGN_YAML.replace(
        'preregistration_hash: ""', f"preregistration_hash: {pin}"
    )
    return load_design(pinned_yaml), pinned_yaml


def test_two_stage_experiment_runs_to_adoption():
    design, pinned_yaml = _pinned_design()
    record = run_two_stage(
        design,
        pinned_yaml,
        stage1_control=ArmReading(arm="control", hits=30, n=500),
        stage1_variants=[
            ArmReading(arm="A", hits=33, n=500),
            ArmReading(arm="B", hits=62, n=500),  # the real effect
            ArmReading(arm="C", hits=29, n=500),
        ],
        stage2_control=ArmReading(arm="control", hits=30, n=500),
        stage2_treatment=ArmReading(arm="B", hits=55, n=500),  # fresh sample
        guardrails=[
            GuardrailReading(
                metric="unsubscribe_rate", control=0.002, treatment=0.0022,
                max_degradation=0.001,
            )
        ],
    )
    assert record.stage1_survivors == ["B"]
    assert record.decision == "adopt" and record.winner == "B"
    assert record.compounding_eligible
    admit_to_compounding(record)  # the boundary opens for adoptions only


def test_guardrails_veto_a_winning_primary():
    design, pinned_yaml = _pinned_design()
    record = run_two_stage(
        design,
        pinned_yaml,
        stage1_control=ArmReading(arm="control", hits=30, n=500),
        stage1_variants=[ArmReading(arm="B", hits=62, n=500)],
        stage2_control=ArmReading(arm="control", hits=30, n=500),
        stage2_treatment=ArmReading(arm="B", hits=55, n=500),
        guardrails=[
            GuardrailReading(
                metric="unsubscribe_rate", control=0.002, treatment=0.006,
                max_degradation=0.001,
            )
        ],
    )
    assert record.decision == "reject"
    assert record.guardrail_vetoes
    with pytest.raises(CompoundingBoundaryError, match="enters"):
        admit_to_compounding(record)


def test_inconclusive_enters_nothing_but_updates_n():
    design, pinned_yaml = _pinned_design()
    record = run_two_stage(
        design,
        pinned_yaml,
        stage1_control=ArmReading(arm="control", hits=30, n=500),
        stage1_variants=[
            ArmReading(arm="A", hits=31, n=500),
            ArmReading(arm="B", hits=29, n=500),
        ],
    )
    assert record.decision == "inconclusive"
    assert not record.compounding_eligible
    assert record.priors_update["n"] == 1500  # the ledger takes the n, only the n
    with pytest.raises(CompoundingBoundaryError):
        admit_to_compounding(record)


def test_post_hoc_edit_voids_the_analysis_itself():
    design, pinned_yaml = _pinned_design()
    edited = pinned_yaml.replace("mde_relative: 0.5", "mde_relative: 0.3")
    with pytest.raises(PreregistrationError):
        run_two_stage(
            design,
            edited,
            stage1_control=ArmReading(arm="control", hits=30, n=500),
            stage1_variants=[ArmReading(arm="B", hits=62, n=500)],
        )


def test_underpowered_design_states_the_required_n():
    result = power_calc(
        baseline=0.05, mde_relative=0.10, arms=6, weekly_traffic=200, max_days=23
    )
    assert result.status == "BLOCKED(INSUFFICIENT_POWER)"
    assert result.n_per_arm > 0 and str(result.n_per_arm) in result.detail
    assert "qualitative test" in result.detail
