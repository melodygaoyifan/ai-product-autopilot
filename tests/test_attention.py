"""v0.46.0 — weekly attention collection, the series the v3.0.0 kill
criterion is falsifiable by (doc 25 §76.4).

The load-bearing assertions are about what the machine REFUSES to do: it
never sets `hours`, never backfills a week, never rewrites one, and never
lets an untracked week count toward or against the streak.
"""

from __future__ import annotations

import datetime
import pathlib

import pytest
import yaml

from autoproduct.attention import (
    BUDGET_HOURS,
    CONSECUTIVE_WEEKS_TO_FIRE,
    AttentionError,
    LogRow,
    append_row,
    collect_floor,
    iso_week,
    load_log,
    streak_state,
    week_window,
)

REPO = pathlib.Path(__file__).resolve().parents[1]


def _log(tmp_path, rows: list[dict]) -> pathlib.Path:
    path = tmp_path / "metrics" / "attention-log.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# a header comment that must survive appends\n"
        + yaml.safe_dump({"log": rows}, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _logged(week: str, hours: float) -> dict:
    return {"week": week, "window": "x..y", "hours": hours, "status": "logged",
            "decided_by": "melody"}


def _untracked(week: str) -> dict:
    return {"week": week, "window": "x..y", "hours": None, "status": "not_tracked"}


# --- week arithmetic ----------------------------------------------------------


def test_iso_week_and_window_round_trip():
    assert iso_week(datetime.date(2026, 7, 27)) == "2026-W31"
    monday, sunday = week_window("2026-W31")
    assert monday == datetime.date(2026, 7, 27)
    assert sunday == datetime.date(2026, 8, 2)
    assert (sunday - monday).days == 6


def test_malformed_week_label_errors():
    for bad in ("2026", "2026-31", "not-a-week", "2026-W99"):
        with pytest.raises(AttentionError):
            week_window(bad)


# --- the floor: measured, never estimated ------------------------------------


def test_floor_is_zero_and_says_so_when_nothing_was_touched(tmp_path):
    floor = collect_floor(tmp_path, "2026-W31")
    assert floor.measured_floor_hours == 0.0
    assert floor.evidence == []
    assert "no timestamped human act found" in floor.summary()


def test_gate_dwell_inside_the_week_becomes_evidence(tmp_path):
    review = tmp_path / ".mas" / "reviews" / "abc123"
    review.mkdir(parents=True)
    (review / "07-escalate.yaml").write_text(
        yaml.safe_dump({"written_at": "2026-07-28T09:00:00+00:00"}), encoding="utf-8"
    )
    (review / "08-final.yaml").write_text(
        yaml.safe_dump({"written_at": "2026-07-28T09:30:00+00:00"}), encoding="utf-8"
    )
    floor = collect_floor(tmp_path, "2026-W31")
    assert [e.kind for e in floor.evidence] == ["gate_dwell"]
    assert floor.measured_floor_hours == 0.5
    assert floor.evidence[0].locator == "reviews/abc123"


def test_dwell_outside_the_week_is_excluded(tmp_path):
    review = tmp_path / ".mas" / "reviews" / "old"
    review.mkdir(parents=True)
    (review / "07-escalate.yaml").write_text(
        yaml.safe_dump({"written_at": "2026-07-01T09:00:00+00:00"}), encoding="utf-8"
    )
    (review / "08-final.yaml").write_text(
        yaml.safe_dump({"written_at": "2026-07-01T10:00:00+00:00"}), encoding="utf-8"
    )
    assert collect_floor(tmp_path, "2026-W31").evidence == []


def test_a_week_long_pause_is_not_a_week_of_attention(tmp_path):
    """A gate left open over a holiday is not attention spent; the dwell
    contribution is capped rather than believed."""
    review = tmp_path / ".mas" / "reviews" / "slow"
    review.mkdir(parents=True)
    (review / "07-escalate.yaml").write_text(
        yaml.safe_dump({"written_at": "2026-07-27T09:00:00+00:00"}), encoding="utf-8"
    )
    (review / "08-final.yaml").write_text(
        yaml.safe_dump({"written_at": "2026-08-02T09:00:00+00:00"}), encoding="utf-8"
    )
    floor = collect_floor(tmp_path, "2026-W31")
    assert floor.measured_floor_hours == 4.0  # the cap, not 144 hours


def test_reviews_that_never_escalated_contribute_nothing(tmp_path):
    review = tmp_path / ".mas" / "reviews" / "clean"
    review.mkdir(parents=True)
    (review / "08-final.yaml").write_text(
        yaml.safe_dump({"written_at": "2026-07-28T09:00:00+00:00"}), encoding="utf-8"
    )
    assert collect_floor(tmp_path, "2026-W31").evidence == []


def test_recorded_gate_decisions_contribute_a_flat_stated_cost(tmp_path):
    product = tmp_path / ".mas" / "product"
    product.mkdir(parents=True)
    (product / "prd-report.yaml").write_text(
        yaml.safe_dump({"decided_at": "2026-07-29T11:00:00+00:00"}), encoding="utf-8"
    )
    sweep = tmp_path / ".mas" / "sweep"
    sweep.mkdir(parents=True)
    (sweep / "pass-1.yaml").write_text(
        yaml.safe_dump({"written_at": "2026-07-30T08:00:00+00:00"}), encoding="utf-8"
    )
    floor = collect_floor(tmp_path, "2026-W31")
    kinds = sorted(e.kind for e in floor.evidence)
    assert kinds == ["product_gate", "sweep_review"]
    assert floor.measured_floor_hours == round((900 + 600) / 3600, 2)


def test_unparseable_artifacts_are_skipped_not_fatal(tmp_path):
    review = tmp_path / ".mas" / "reviews" / "broken"
    review.mkdir(parents=True)
    (review / "07-escalate.yaml").write_text("not: [valid", encoding="utf-8")
    (review / "08-final.yaml").write_text("also broken: [", encoding="utf-8")
    assert collect_floor(tmp_path, "2026-W31").evidence == []


# --- the log: append-only, human-authored ------------------------------------


def test_appending_preserves_the_header_and_prior_rows(tmp_path):
    _log(tmp_path, [_untracked("2026-W30")])
    append_row(tmp_path, LogRow(week="2026-W31", window="a..b", hours=5.5,
                                status="logged", decided_by="melody"))
    text = (tmp_path / "metrics" / "attention-log.yaml").read_text()
    assert text.startswith("# a header comment that must survive appends")
    rows = load_log(tmp_path)
    assert [r.week for r in rows] == ["2026-W30", "2026-W31"]
    assert rows[1].hours == 5.5 and rows[1].decided_by == "melody"


def test_a_logged_week_is_never_silently_rewritten(tmp_path):
    _log(tmp_path, [_logged("2026-W31", 3.0)])
    with pytest.raises(AttentionError, match="append-only"):
        append_row(tmp_path, LogRow(week="2026-W31", window="a..b", hours=9.0,
                                    status="logged", decided_by="someone"))
    assert load_log(tmp_path)[0].hours == 3.0  # untouched


def test_malformed_log_errors_rather_than_starting_over(tmp_path):
    path = tmp_path / "metrics" / "attention-log.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("log: [unclosed", encoding="utf-8")
    with pytest.raises(AttentionError, match="not parseable"):
        load_log(tmp_path)


# --- the streak: what the criterion actually reads ---------------------------


def test_four_consecutive_over_budget_weeks_fire_the_criterion(tmp_path):
    _log(tmp_path, [_logged(f"2026-W{30 + i}", 5.0) for i in range(4)])
    state = streak_state(tmp_path)
    assert state.streak == 4 and state.fires is True
    assert "HAS FIRED" in state.detail and "invariant 14.20" in state.detail


def test_three_over_budget_weeks_do_not_fire(tmp_path):
    _log(tmp_path, [_logged(f"2026-W{30 + i}", 5.0) for i in range(3)])
    state = streak_state(tmp_path)
    assert state.streak == 3 and state.fires is False
    assert "1 more would fire it" in state.detail


def test_a_week_under_budget_resets_the_streak(tmp_path):
    _log(tmp_path, [_logged("2026-W30", 5.0), _logged("2026-W31", 5.0),
                    _logged("2026-W32", 1.0), _logged("2026-W33", 5.0)])
    assert streak_state(tmp_path).streak == 1


def test_an_untracked_week_breaks_the_streak_without_counting_either_way(tmp_path):
    """The log's own rule: a criterion cannot fire on uncollected data, and
    it cannot be declared safe on it either."""
    _log(tmp_path, [_logged("2026-W30", 9.0), _logged("2026-W31", 9.0),
                    _untracked("2026-W32"),
                    _logged("2026-W33", 9.0), _logged("2026-W34", 9.0)])
    state = streak_state(tmp_path)
    assert state.streak == 2  # not 4
    assert state.fires is False
    assert state.untracked_weeks == 1 and state.logged_weeks == 4
    assert "untracked breaks a streak" in state.detail


def test_exactly_at_budget_does_not_count_as_over(tmp_path):
    _log(tmp_path, [_logged(f"2026-W{30 + i}", BUDGET_HOURS) for i in range(4)])
    assert streak_state(tmp_path).streak == 0


def test_budget_and_window_match_the_prd():
    """These constants are the PRD's, not this module's invention."""
    prd = yaml.safe_load((REPO / "launch" / "prd.yaml").read_text(encoding="utf-8"))
    criteria = " ".join((prd.get("prd") or {}).get("kill_criteria") or [])
    assert str(BUDGET_HOURS) in criteria
    assert str(CONSECUTIVE_WEEKS_TO_FIRE) in criteria


# --- the CLI contract --------------------------------------------------------


def test_cli_reports_without_logging_and_requires_an_author(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from autoproduct.cli import app

    _log(tmp_path, [_untracked("2026-W30")])
    runner = CliRunner()
    # Read-only invocation must not write a row.
    result = runner.invoke(app, ["attention", "--week", "2026-W31",
                                 "--repo-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert [r.week for r in load_log(tmp_path)] == ["2026-W30"]
    assert "the logged number is yours" in result.output

    # Logging without an author is refused: a number here has one.
    result = runner.invoke(app, ["attention", "--week", "2026-W31",
                                 "--repo-dir", str(tmp_path),
                                 "--confirm-hours", "6"])
    assert result.exit_code == 2
    assert "--by is required" in result.output
    assert [r.week for r in load_log(tmp_path)] == ["2026-W30"]


def test_cli_logs_the_humans_number_and_records_the_floor_beside_it(tmp_path):
    from typer.testing import CliRunner

    from autoproduct.cli import app

    _log(tmp_path, [])
    review = tmp_path / ".mas" / "reviews" / "r1"
    review.mkdir(parents=True)
    (review / "07-escalate.yaml").write_text(
        yaml.safe_dump({"written_at": "2026-07-28T09:00:00+00:00"}), encoding="utf-8")
    (review / "08-final.yaml").write_text(
        yaml.safe_dump({"written_at": "2026-07-28T09:20:00+00:00"}), encoding="utf-8")

    result = CliRunner().invoke(app, [
        "attention", "--week", "2026-W31", "--repo-dir", str(tmp_path),
        "--confirm-hours", "6.5", "--by", "melody", "--note", "release week",
    ])
    assert result.exit_code == 0, result.output
    row = load_log(tmp_path)[0]
    assert row.hours == 6.5  # the human's number
    assert row.measured_floor_hours == 0.33  # the machine's floor, beside it
    assert row.evidence_count == 1
    assert row.decided_by == "melody" and row.note == "release week"


def test_cli_exits_3_and_demands_a_human_decision_when_the_criterion_fires(tmp_path):
    from typer.testing import CliRunner

    from autoproduct.cli import app

    _log(tmp_path, [_logged(f"2026-W{30 + i}", 9.0) for i in range(3)])
    result = CliRunner().invoke(app, [
        "attention", "--week", "2026-W33", "--repo-dir", str(tmp_path),
        "--confirm-hours", "9.0", "--by", "melody",
    ])
    assert result.exit_code == 3
    # rich word-wraps at terminal width, so assert on normalized output.
    flat = " ".join(result.output.split())
    assert "HAS FIRED" in flat
    assert "requires YOUR recorded decision" in flat
    assert "Nothing here decides it" in flat
