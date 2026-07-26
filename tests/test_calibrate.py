"""Scanner-calibration report (§19 G7, R-G3). Hermetic — fake scanners via
sys.executable one-liners, so the report logic is tested without any real
toolchain installed."""

import sys
from pathlib import Path

import pytest
import yaml

from autoproduct.adoption import calibration_report, write_calibration_report
from autoproduct.adoption.calibrate import CalibrationReport


def _manifest(tmp_path: Path, defects: list[dict]) -> Path:
    path = tmp_path / "seeded.yaml"
    path.write_text(yaml.safe_dump({"defects": defects}), encoding="utf-8")
    return path


def _toolchains(tmp_path: Path, **slots: list[str]) -> None:
    config = tmp_path / ".mas" / "toolchains.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(yaml.safe_dump({"java": slots}), encoding="utf-8")


def _echo(text: str, code: int = 0) -> list[str]:
    return [sys.executable, "-c", f"print({text!r}); raise SystemExit({code})"]


def test_hit_and_miss_split_with_slot_output(tmp_path):
    manifest = _manifest(tmp_path, [
        {"id": "D1", "slot": "sast", "pattern": "CWE-89", "note": "sqli"},
        {"id": "D2", "slot": "sast", "pattern": "CWE-79", "note": "xss"},
    ])
    _toolchains(tmp_path, sast=_echo("found CWE-89 in Payments", 1))
    report = calibration_report(tmp_path, "java", manifest)
    if report.catch_rate != 0.5 or report.caught != 1:
        pytest.fail(f"catch rate wrong: {report}")
    if [h.defect_id for h in report.hits] != ["D1"]:
        pytest.fail("D1 should hit")
    if [m.defect_id for m in report.misses] != ["D2"]:
        pytest.fail("D2 should miss")
    # the operator needs the actual output to pick a new pattern
    sast_out = [s for s in report.slot_outputs if s.slot == "sast"][0]
    if "CWE-89" not in sast_out.output:
        pytest.fail("slot output must be captured for recalibration")


def test_miss_on_a_slot_that_ran_flags_recalibration(tmp_path):
    manifest = _manifest(tmp_path, [
        {"id": "D1", "slot": "sast", "pattern": "WRONGLABEL", "note": "x"},
    ])
    _toolchains(tmp_path, sast=_echo("actual scanner says CWE-89", 1))
    report = calibration_report(tmp_path, "java", manifest)
    if not report.needs_recalibration:
        pytest.fail("a miss on a slot that RAN is a bad pattern → recalibrate")


def test_skipped_slot_is_not_a_recalibration_signal(tmp_path):
    # binary absent → the fix is 'install the scanner', not 'fix the pattern'
    manifest = _manifest(tmp_path, [
        {"id": "D1", "slot": "deps", "pattern": "CVE-1", "note": "x"},
    ])
    _toolchains(tmp_path, deps=["definitely-not-a-binary-xyz"])
    report = calibration_report(tmp_path, "java", manifest)
    if report.needs_recalibration:
        pytest.fail("a skipped slot is a missing binary, not a bad pattern")
    # every uninstalled builtin slot skips too; the point is deps is among them
    if "deps" not in report.skipped_slots:
        pytest.fail(f"the missing-binary slot must be reported: {report.skipped_slots}")


def test_all_patterns_correct_needs_no_recalibration(tmp_path):
    manifest = _manifest(tmp_path, [
        {"id": "D1", "slot": "sast", "pattern": "CVE-89", "note": "x"},
    ])
    _toolchains(tmp_path, sast=_echo("CVE-89 here", 1))
    report = calibration_report(tmp_path, "java", manifest)
    if report.needs_recalibration or report.catch_rate != 1.0:
        pytest.fail(f"correct patterns must be clean: {report}")


def test_report_written_to_mas_calibration(tmp_path):
    manifest = _manifest(tmp_path, [{"id": "D1", "slot": "sast", "pattern": "X"}])
    _toolchains(tmp_path, sast=_echo("X", 0))
    path = write_calibration_report(tmp_path, "java", manifest)
    if path != tmp_path / ".mas" / "calibration" / "java.yaml":
        pytest.fail(f"unexpected path: {path}")
    loaded = CalibrationReport(**yaml.safe_load(path.read_text(encoding="utf-8")))
    if loaded.language != "java":
        pytest.fail("round-trip failed")


def test_out_base_separates_run_dir_from_report_dir(tmp_path):
    # the container runs the lane in one place, writes the report to the
    # mounted CWD in another — reports must survive, not land in the lane
    lane = tmp_path / "lane"
    lane.mkdir()
    manifest = _manifest(lane, [{"id": "D1", "slot": "sast", "pattern": "X"}])
    _toolchains(lane, sast=_echo("X", 0))
    out = tmp_path / "cwd"
    out.mkdir()
    path = write_calibration_report(lane, "java", manifest, out_base=out)
    if path != out / ".mas" / "calibration" / "java.yaml" or not path.exists():
        pytest.fail(f"report must land under out_base, not the lane: {path}")
    if (lane / ".mas" / "calibration").exists():
        pytest.fail("nothing should be written into the lane dir")


# --- the bundled seeded lanes calibrate against fake scanners end-to-end ----------

SEEDED = Path(__file__).parent / "toolchains" / "seeded"


@pytest.mark.parametrize("language", ["java", "dotnet"])
def test_bundled_lane_report_covers_every_defect(tmp_path, language):
    """Without real scanners every slot is skipped, but the report must still
    enumerate every manifest defect as a miss with a reason — never silently
    drop one."""
    lane = SEEDED / language
    report = calibration_report(lane, language, lane / "seeded.yaml")
    manifest_ids = {d["id"] for d in yaml.safe_load(
        (lane / "seeded.yaml").read_text(encoding="utf-8"))["defects"]}
    seen = {m.defect_id for m in report.misses} | {h.defect_id for h in report.hits}
    if seen != manifest_ids:
        pytest.fail(f"{language}: report dropped defects: {manifest_ids - seen}")
