"""Data-pipeline det_tools core (§18.48.1, §19 G10-G12). Hermetic."""

from pathlib import Path

import pytest
import yaml

from ai_venture_studio.adoption import (
    contract_check,
    eval_gate,
    idempotency_check,
    load_contract,
    pin_baseline,
)


# --- eval gate -----------------------------------------------------------------

def test_pin_then_pass_within_tolerance(tmp_path):
    pin_baseline(tmp_path, {"accuracy": 0.91, "f1": 0.85}, tolerance=0.01)
    result = eval_gate(tmp_path, {"accuracy": 0.905, "f1": 0.86})
    if not result.passed:
        pytest.fail(f"within tolerance must pass: {result.verdicts}")


def test_regression_beyond_tolerance_fails(tmp_path):
    pin_baseline(tmp_path, {"accuracy": 0.91}, tolerance=0.01)
    result = eval_gate(tmp_path, {"accuracy": 0.88})
    verdict = result.verdicts[0]
    if result.passed or verdict.status != "regression":
        pytest.fail(f"0.88 vs 0.91±0.01 must regress: {verdict}")
    if verdict.delta != -0.03:
        pytest.fail(f"delta must be reported: {verdict.delta}")


def test_missing_pinned_metric_fails(tmp_path):
    pin_baseline(tmp_path, {"accuracy": 0.91, "f1": 0.85})
    result = eval_gate(tmp_path, {"accuracy": 0.92})
    statuses = {v.metric: v.status for v in result.verdicts}
    if result.passed or statuses["f1"] != "missing":
        pytest.fail("an unmeasured pinned metric never reads as unregressed")


def test_unpinned_metric_is_visible_but_not_fatal(tmp_path):
    pin_baseline(tmp_path, {"accuracy": 0.91})
    result = eval_gate(tmp_path, {"accuracy": 0.91, "recall": 0.7})
    if not result.passed or result.unpinned != ["recall"]:
        pytest.fail(f"new metric must surface as unpinned: {result.verdicts}")


def test_gate_without_baseline_refuses(tmp_path):
    with pytest.raises(FileNotFoundError, match="not a gate"):
        eval_gate(tmp_path, {"accuracy": 0.9})


def test_empty_pin_refused(tmp_path):
    with pytest.raises(ValueError, match="empty baseline"):
        pin_baseline(tmp_path, {})


def test_pin_is_a_reviewable_file(tmp_path):
    path = pin_baseline(tmp_path, {"accuracy": 0.91}, tolerance=0.02)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data != {"tolerance": 0.02, "metrics": {"accuracy": 0.91}}:
        pytest.fail(f"baseline file must be the whole story: {data}")


# --- backfill idempotency ---------------------------------------------------------

def _run_dir(tmp_path: Path, name: str, files: dict[str, str]) -> Path:
    root = tmp_path / name
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    root.mkdir(exist_ok=True)
    return root


def test_identical_runs_pass(tmp_path):
    a = _run_dir(tmp_path, "a", {"part=1/out.csv": "1,2\n", "part=2/out.csv": "3\n"})
    b = _run_dir(tmp_path, "b", {"part=1/out.csv": "1,2\n", "part=2/out.csv": "3\n"})
    if not idempotency_check(a, b).identical:
        pytest.fail("byte-identical trees must pass")


def test_content_and_structure_diffs_named(tmp_path):
    a = _run_dir(tmp_path, "a", {"x.csv": "1\n", "only_a.csv": "z\n"})
    b = _run_dir(tmp_path, "b", {"x.csv": "2\n", "only_b.csv": "z\n"})
    result = idempotency_check(a, b)
    if result.identical:
        pytest.fail("must fail")
    if (result.content_diffs, result.only_in_first, result.only_in_second) != (
        ["x.csv"], ["only_a.csv"], ["only_b.csv"]
    ):
        pytest.fail(f"diffs must be named: {result}")


def test_empty_runs_are_an_error_not_a_pass(tmp_path):
    a = _run_dir(tmp_path, "a", {})
    b = _run_dir(tmp_path, "b", {})
    with pytest.raises(ValueError, match="nothing was verified"):
        idempotency_check(a, b)


def test_missing_run_dir_refused(tmp_path):
    a = _run_dir(tmp_path, "a", {"x.csv": "1\n"})
    with pytest.raises(FileNotFoundError):
        idempotency_check(a, tmp_path / "nope")


# --- data contract -----------------------------------------------------------------

CONTRACT = [
    {"name": "order_id", "type": "int", "required": True, "not_null": True},
    {"name": "amount", "type": "float", "required": True, "not_null": True},
    {"name": "note", "type": "str", "required": False},
]


def test_conforming_rows_pass():
    rows = [{"order_id": 1, "amount": 9.5, "note": "ok"}, {"order_id": 2, "amount": 3}]
    if contract_check(CONTRACT, rows) != []:
        pytest.fail("conforming rows must pass")


def test_violations_carry_row_field_rule():
    rows = [
        {"order_id": None, "amount": "9.5"},   # null + type
        {"amount": 1.0},                        # missing required
    ]
    violations = contract_check(CONTRACT, rows)
    tags = {(v.row, v.field, v.rule) for v in violations}
    if tags != {(0, "order_id", "not_null"), (0, "amount", "type"),
                (1, "order_id", "required")}:
        pytest.fail(f"unexpected violations: {tags}")


def test_bool_is_not_an_int():
    violations = contract_check(CONTRACT, [{"order_id": True, "amount": 1.0}])
    if not any(v.rule == "type" for v in violations):
        pytest.fail("True must not satisfy an int column — the classic silent flood")


def test_empty_rows_are_a_violation():
    violations = contract_check(CONTRACT, [])
    if violations[0].rule != "non_empty":
        pytest.fail("a boundary that saw no rows verified no contract")


def test_contract_file_validation(tmp_path):
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.safe_dump({"fields": CONTRACT}), encoding="utf-8")
    if load_contract(path) != CONTRACT:
        pytest.fail("round-trip failed")
    path.write_text(yaml.safe_dump({"fields": [{"name": "x", "type": "decimal"}]}))
    with pytest.raises(ValueError, match="decimal"):
        load_contract(path)
    path.write_text(yaml.safe_dump({"fields": []}))
    with pytest.raises(ValueError, match="no fields"):
        load_contract(path)


# --- external data-check wrappers (data_tools) -----------------------------------

def test_dbt_autodetected_and_overrides_merged(tmp_path):
    from ai_venture_studio.adoption import data_check_spec

    if data_check_spec(tmp_path) != {}:
        pytest.fail("no dbt, no config → empty spec")
    (tmp_path / "dbt_project.yml").write_text("name: pipeline\n", encoding="utf-8")
    config = tmp_path / ".mas" / "data-checks.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        yaml.safe_dump({"checks": {"dag_import": ["python", "-c", "import dags"]}}),
        encoding="utf-8",
    )
    spec = data_check_spec(tmp_path)
    if set(spec) != {"dbt_compile", "dbt_test", "dag_import"}:
        pytest.fail(f"spec wrong: {spec}")


def test_bad_check_config_rejected(tmp_path):
    from ai_venture_studio.adoption import data_check_spec

    config = tmp_path / ".mas" / "data-checks.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(yaml.safe_dump({"checks": {"x": "not-a-list"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="argv list"):
        data_check_spec(tmp_path)


def test_unconfigured_workspace_is_loudly_unchecked(tmp_path):
    from ai_venture_studio.adoption import run_data_checks

    results = run_data_checks(tmp_path)
    if len(results) != 1 or results[0].status != "skipped":
        pytest.fail(f"empty spec must report, not pass: {results}")
    if "not clean" not in results[0].detail:
        pytest.fail("the report must say NOT checked, not clean")


def test_declared_checks_run_and_capture(tmp_path):
    import sys

    from ai_venture_studio.adoption import run_data_checks

    config = tmp_path / ".mas" / "data-checks.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(yaml.safe_dump({"checks": {
        "ok": [sys.executable, "-c", "print('rows valid')"],
        "broken_contract": [sys.executable, "-c", "raise SystemExit(2)"],
        "missing_tool": ["definitely-not-a-binary-xyz"],
    }}), encoding="utf-8")
    by_name = {r.slot: r for r in run_data_checks(tmp_path)}
    if by_name["ok"].status != "clean" or "rows valid" not in by_name["ok"].output:
        pytest.fail(f"clean check wrong: {by_name['ok']}")
    if by_name["broken_contract"].status != "findings":
        pytest.fail("non-zero exit must be findings")
    if by_name["missing_tool"].status != "skipped":
        pytest.fail("missing binary must be skipped, loudly")
