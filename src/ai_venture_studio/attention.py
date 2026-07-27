"""Weekly maintenance-attention collection (doc 25 §76.4, metrics/).

The launch PRD's only kill criterion is falsifiable by one series: hours of
human maintenance attention per week. Four consecutive logged weeks over
budget fires Gate PL5. As of v0.45 that series had one `not_tracked` row,
because logging it was a manual habit — and a manual habit that lapses
doesn't just lose a week, it resets the streak the criterion depends on.

This module removes the *unautomated* half of that problem without touching
the human half:

- **The machine measures a floor, not the number.** Gate dwell, escalation
  acks, product-gate approvals and sweep reviews carry real timestamps in
  `.mas/`, and their sum is a lower bound on attention actually spent —
  observable, reproducible, cited to the artifacts it came from.
- **The human sets `hours`.** A floor is not the total: reading a review
  without touching a gate, thinking in the shower, and answering a founder's
  question all count and none leave a timestamp. So `hours` stays a human
  entry and `status: logged` stays a human act. The collector's job is to
  make that entry a confirmation rather than an act of recall.
- **Nothing is ever invented or backfilled.** A week with no confirmation
  stays `not_tracked` with `hours: null`, exactly as the log's own header
  demands, and the log is append-only: an existing week is never rewritten.
  The doc's remark that "a habit of not tracking is itself a Gate-PL5
  talking point" survives intact — this makes the habit cheap, not automatic.
"""

from __future__ import annotations

import datetime
import pathlib

import yaml
from pydantic import BaseModel, Field

ATTENTION_LOG = pathlib.Path("metrics") / "attention-log.yaml"
# The budget the launch PRD's kill criterion is stated against (doc 25 §76.4).
BUDGET_HOURS = 4.0
CONSECUTIVE_WEEKS_TO_FIRE = 4


class AttentionEvidence(BaseModel):
    """One observable, timestamped act of human attention."""

    kind: str  # gate_dwell | escalation_ack | product_gate | sweep_review
    locator: str  # the artifact it was measured from
    seconds: float


class WeekFloor(BaseModel):
    week: str  # ISO year-week, e.g. 2026-W31
    window: str  # YYYY-MM-DD..YYYY-MM-DD
    evidence: list[AttentionEvidence] = Field(default_factory=list)

    @property
    def measured_floor_hours(self) -> float:
        return round(sum(e.seconds for e in self.evidence) / 3600.0, 2)

    def summary(self) -> str:
        by_kind: dict[str, int] = {}
        for item in self.evidence:
            by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
        parts = ", ".join(f"{n}× {k}" for k, n in sorted(by_kind.items()))
        return (
            f"{self.week}: observable floor {self.measured_floor_hours}h"
            f"{f' from {parts}' if parts else ' — no timestamped human act found'}"
        )


class LogRow(BaseModel):
    week: str
    window: str
    hours: float | None = None
    status: str = "not_tracked"  # logged | not_tracked
    note: str = ""
    decided_by: str = ""
    measured_floor_hours: float | None = None
    evidence_count: int | None = None


class AttentionError(RuntimeError):
    pass


def iso_week(day: datetime.date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_window(week: str) -> tuple[datetime.date, datetime.date]:
    """Monday..Sunday for an ISO year-week label."""
    try:
        year_s, week_s = week.split("-W")
        monday = datetime.date.fromisocalendar(int(year_s), int(week_s), 1)
    except (ValueError, IndexError) as exc:
        raise AttentionError(f"{week!r} is not an ISO year-week (e.g. 2026-W31)") from exc
    return monday, monday + datetime.timedelta(days=6)


def _in_window(stamp: str, start: datetime.date, end: datetime.date) -> bool:
    try:
        moment = datetime.datetime.fromisoformat(stamp)
    except (ValueError, TypeError):
        return False
    return start <= moment.date() <= end


def collect_floor(repo_dir: str | pathlib.Path, week: str) -> WeekFloor:
    """Sum the timestamped human acts inside a week.

    Every source is an artifact the system already writes for its own
    reasons; nothing new is instrumented, and nothing is estimated.
    """
    root = pathlib.Path(repo_dir)
    start, end = week_window(week)
    evidence: list[AttentionEvidence] = []

    # 1. Review gates the human actually paused at: escalate → final dwell is
    #    time a person spent deciding (the same measurement dwell.py uses to
    #    detect rubber-stamping).
    reviews = root / ".mas" / "reviews"
    if reviews.is_dir():
        for review_dir in sorted(p for p in reviews.iterdir() if p.is_dir()):
            escalate = sorted(review_dir.glob("[0-9]*-escalate.yaml"))
            final = sorted(review_dir.glob("[0-9]*-final.yaml"))
            if not escalate or not final:
                continue
            try:
                opened = yaml.safe_load(escalate[0].read_text(encoding="utf-8")) or {}
                closed = yaml.safe_load(final[-1].read_text(encoding="utf-8")) or {}
                start_ts = str(opened.get("written_at", ""))
                end_ts = str(closed.get("written_at", ""))
                if not _in_window(end_ts, start, end):
                    continue
                seconds = (
                    datetime.datetime.fromisoformat(end_ts)
                    - datetime.datetime.fromisoformat(start_ts)
                ).total_seconds()
            except (OSError, ValueError, yaml.YAMLError):
                continue
            if seconds <= 0:
                continue
            evidence.append(AttentionEvidence(
                kind="gate_dwell", locator=f"reviews/{review_dir.name}",
                seconds=min(seconds, 4 * 3600),  # a week-long pause is not attention
            ))

    # 2. Recorded human gate decisions elsewhere: each is an act with a
    #    timestamp but no duration, so it contributes a flat, stated cost
    #    rather than a guess dressed as a measurement.
    for pattern, kind, flat_seconds in (
        (".mas/product/*-report.yaml", "product_gate", 900),
        (".mas/sweep/*.yaml", "sweep_review", 600),
        (".mas/cab/*.yaml", "product_gate", 900),
    ):
        for path in sorted(root.glob(pattern)):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            stamp = str(
                data.get("decided_at") or data.get("written_at")
                or data.get("approved_at") or ""
            )
            if not stamp:
                # Fall back to the file's own mtime, which is when the human
                # act landed on disk — labeled by kind, never as a duration.
                stamp = datetime.datetime.fromtimestamp(
                    path.stat().st_mtime, datetime.UTC
                ).isoformat()
            if _in_window(stamp, start, end):
                evidence.append(AttentionEvidence(
                    kind=kind,
                    locator=str(path.relative_to(root)),
                    seconds=float(flat_seconds),
                ))

    return WeekFloor(
        week=week, window=f"{start.isoformat()}..{end.isoformat()}", evidence=evidence
    )


def load_log(repo_dir: str | pathlib.Path) -> list[LogRow]:
    path = pathlib.Path(repo_dir) / ATTENTION_LOG
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise AttentionError(f"{path} is not parseable YAML: {exc}") from exc
    rows = raw.get("log") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise AttentionError(f"{path} must hold a `log:` list")
    return [LogRow.model_validate(r) for r in rows]


def append_row(repo_dir: str | pathlib.Path, row: LogRow) -> pathlib.Path:
    """Append-only: an existing week is never rewritten.

    Correcting a logged week is a human edit to the file with its own note,
    not something a command does silently — the series is the evidence the
    kill criterion rests on.
    """
    path = pathlib.Path(repo_dir) / ATTENTION_LOG
    existing = load_log(repo_dir)
    if any(r.week == row.week for r in existing):
        raise AttentionError(
            f"{row.week} is already in the log — the series is append-only; "
            "correct it by editing the file with a note saying why"
        )
    header = ""
    if path.exists():
        text = path.read_text(encoding="utf-8")
        header = "".join(
            line for line in text.splitlines(keepends=True) if line.startswith("#")
        )
    rows = [r.model_dump(exclude_none=True) for r in [*existing, row]]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        header + yaml.safe_dump({"log": rows}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


class StreakState(BaseModel):
    budget_hours: float = BUDGET_HOURS
    needed: int = CONSECUTIVE_WEEKS_TO_FIRE
    streak: int = 0  # consecutive logged weeks over budget, most recent last
    logged_weeks: int = 0
    untracked_weeks: int = 0
    fires: bool = False
    detail: str = ""


def streak_state(repo_dir: str | pathlib.Path) -> StreakState:
    """How close the kill criterion is to firing, mechanically.

    A `not_tracked` week breaks the streak rather than counting either way —
    the log's own rule. The criterion cannot fire on uncollected data, and it
    cannot be declared safe on it either.
    """
    rows = load_log(repo_dir)
    logged = [r for r in rows if r.status == "logged" and r.hours is not None]
    untracked = [r for r in rows if r.status != "logged"]
    streak = 0
    for row in rows:
        if row.status != "logged" or row.hours is None:
            streak = 0
            continue
        streak = streak + 1 if row.hours > BUDGET_HOURS else 0
    fires = streak >= CONSECUTIVE_WEEKS_TO_FIRE
    if fires:
        detail = (
            f"{streak} consecutive logged weeks over {BUDGET_HOURS}h — the kill "
            "criterion HAS FIRED; Gate PL5 requires a recorded human decision "
            "(invariant 14.20)"
        )
    else:
        remaining = CONSECUTIVE_WEEKS_TO_FIRE - streak
        detail = (
            f"{streak}/{CONSECUTIVE_WEEKS_TO_FIRE} consecutive logged weeks over "
            f"{BUDGET_HOURS}h; {remaining} more would fire it. "
            f"{len(logged)} logged week(s), {len(untracked)} untracked "
            "(untracked breaks a streak rather than counting either way)"
        )
    return StreakState(
        streak=streak, logged_weeks=len(logged), untracked_weeks=len(untracked),
        fires=fires, detail=detail,
    )
