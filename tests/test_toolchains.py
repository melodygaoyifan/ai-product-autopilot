"""Language toolchains as fixture-gated det_tools (§18.47.2, §19 G7-G9).
Hermetic: slot argv point at sys.executable one-liners or missing binaries."""

import sys
from pathlib import Path

import pytest
import yaml

from autoproduct.adoption import (
    benchmark_toolchain,
    load_seeded_manifest,
    register_toolchain,
    run_toolchain,
    toolchain_banner,
    toolchain_spec,
)

PY = sys.executable


def _echo(text: str, code: int = 0) -> list[str]:
    return [PY, "-c", f"print({text!r}); raise SystemExit({code})"]


def _spec(**slots: list[str]) -> dict[str, list[str]]:
    return slots


# --- slot execution: availability gating is the contract ----------------------

def test_missing_binary_is_skipped_loudly(tmp_path):
    report = run_toolchain(
        tmp_path, "java", spec=_spec(lint=["definitely-not-a-binary-xyz", "src"])
    )
    result = report.results[0]
    if result.status != "skipped" or "not on PATH" not in result.detail:
        pytest.fail(f"missing scanner must be loud: {result}")
    if report.skipped_slots != ["lint"]:
        pytest.fail("skipped slots must be enumerable for the banner")


def test_exit_codes_map_to_clean_and_findings(tmp_path):
    report = run_toolchain(
        tmp_path, "java",
        spec=_spec(lint=_echo("ok", 0), sast=_echo("CWE-89 hit", 1)),
    )
    by_slot = {r.slot: r for r in report.results}
    if by_slot["lint"].status != "clean" or by_slot["sast"].status != "findings":
        pytest.fail(f"status mapping wrong: {by_slot}")
    if "CWE-89" not in by_slot["sast"].output:
        pytest.fail("slot output must be captured for the benchmark")


def test_unknown_language_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown language"):
        toolchain_spec(tmp_path, "cobol")


def test_project_overrides_replace_builtin_argv(tmp_path):
    config = tmp_path / ".mas" / "toolchains.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        yaml.safe_dump({"java": {"tests": ["gradle", "test"]}}), encoding="utf-8"
    )
    spec = toolchain_spec(tmp_path, "java")
    if spec["tests"] != ["gradle", "test"]:
        pytest.fail("Gradle shop must be able to override the Maven default")
    if spec["lint"][0] != "checkstyle":
        pytest.fail("unoverridden slots keep builtin argv")


def test_override_of_unknown_slot_rejected(tmp_path):
    config = tmp_path / ".mas" / "toolchains.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        yaml.safe_dump({"java": {"format": ["gjf"]}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="unknown slot"):
        toolchain_spec(tmp_path, "java")


# --- seeded-defect benchmark ---------------------------------------------------

def _manifest(tmp_path: Path, defects: list[dict]) -> Path:
    path = tmp_path / "seeded.yaml"
    path.write_text(yaml.safe_dump({"defects": defects}), encoding="utf-8")
    return path


def test_catch_and_miss_measured_from_output(tmp_path):
    manifest = load_seeded_manifest(_manifest(tmp_path, [
        {"id": "D1", "slot": "sast", "pattern": "CWE-89"},
        {"id": "D2", "slot": "sast", "pattern": "CWE-79"},
    ]))
    report = run_toolchain(tmp_path, "java", spec=_spec(sast=_echo("found CWE-89", 1)))
    result = benchmark_toolchain(report, manifest)
    caught = {o.defect_id: o.caught for o in result.outcomes}
    if caught != {"D1": True, "D2": False}:
        pytest.fail(f"benchmark wrong: {caught}")
    if result.catch_rate != 0.5:
        pytest.fail(f"catch rate wrong: {result.catch_rate}")


def test_skipped_slot_catches_nothing(tmp_path):
    manifest = load_seeded_manifest(_manifest(tmp_path, [
        {"id": "D1", "slot": "deps", "pattern": "CVE-2026-1"},
    ]))
    report = run_toolchain(
        tmp_path, "java", spec=_spec(deps=["definitely-not-a-binary-xyz"])
    )
    outcome = benchmark_toolchain(report, manifest).outcomes[0]
    if outcome.caught or "skipped" not in outcome.detail:
        pytest.fail("a missing scanner must count as a miss, with the reason named")


def test_empty_manifest_rejected(tmp_path):
    with pytest.raises(ValueError, match="no defects"):
        load_seeded_manifest(_manifest(tmp_path, []))


def test_manifest_missing_fields_rejected(tmp_path):
    with pytest.raises(ValueError, match="missing.*pattern"):
        load_seeded_manifest(_manifest(tmp_path, [{"id": "D1", "slot": "sast"}]))


def test_manifest_unknown_slot_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown slot"):
        load_seeded_manifest(_manifest(tmp_path, [
            {"id": "D1", "slot": "format", "pattern": "x"},
        ]))


# --- registration: the fixture gate for toolchains (F-18.4) --------------------

def _benchmarked(tmp_path: Path, hits: int, total: int):
    defects = [
        {"id": f"D{i}", "slot": "sast", "pattern": f"HIT-{i}" if i < hits else "MISS"}
        for i in range(total)
    ]
    manifest = load_seeded_manifest(_manifest(tmp_path, defects))
    output = " ".join(f"HIT-{i}" for i in range(hits))
    report = run_toolchain(tmp_path, "java", spec=_spec(sast=_echo(output, 1)))
    return benchmark_toolchain(report, manifest)


def test_within_margin_registers(tmp_path):
    record = register_toolchain(
        tmp_path, _benchmarked(tmp_path, hits=9, total=10),
        baseline_rate=0.95, parity_margin=0.10,
    )
    if record.status != "registered" or record.gaps:
        pytest.fail(f"0.90 vs 0.95-0.10 floor must register: {record}")
    banner = toolchain_banner(tmp_path, "java")
    if "registered" not in banner or "90%" not in banner:
        pytest.fail(f"banner wrong: {banner}")


def test_below_margin_is_provisional_with_named_gaps(tmp_path):
    record = register_toolchain(
        tmp_path, _benchmarked(tmp_path, hits=5, total=10),
        baseline_rate=0.95, parity_margin=0.10,
    )
    if record.status != "provisional" or record.gaps != ["sast"]:
        pytest.fail(f"0.50 must be provisional with sast named: {record}")
    banner = toolchain_banner(tmp_path, "java")
    if "PROVISIONAL" not in banner or "sast" not in banner:
        pytest.fail(f"F-18.4: banner must carry the gap: {banner}")


def test_record_persisted_to_registry(tmp_path):
    register_toolchain(tmp_path, _benchmarked(tmp_path, 10, 10), baseline_rate=1.0)
    data = yaml.safe_load(
        (tmp_path / ".mas" / "toolchains" / "java.yaml").read_text(encoding="utf-8")
    )
    if data["status"] != "registered" or data["catch_rate"] != 1.0:
        pytest.fail(f"registry record wrong: {data}")


def test_unmeasured_language_has_no_banner(tmp_path):
    if toolchain_banner(tmp_path, "dotnet") is not None:
        pytest.fail("unmeasured must not read as registered")


def test_bad_baseline_rejected(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        register_toolchain(tmp_path, _benchmarked(tmp_path, 1, 1), baseline_rate=1.5)


# --- workspace data profile (§18.48.1) -----------------------------------------

def test_data_profile_available_for_init():
    from autoproduct.upstream.workspace import available_profiles, load_profile

    if "data" not in available_profiles():
        pytest.fail("data profile missing from profiles/")
    profile = load_profile("data")
    text = yaml.safe_dump(profile)
    for expected in ("data contract", "eval set", "idempotent", "forbidden_autonomous"):
        if expected not in text:
            pytest.fail(f"data profile missing {expected!r}")
