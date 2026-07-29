"""The spend ledger and the cost gate.

`observability.py` could already price a call (`estimate_cost`), total a month
(`month_spend`), and compare against a cap (`cap_check`) — and none of it was
reachable, because nothing ever *recorded* a call. `cap_check` had no
production caller and there was no ledger for it to read. Cost was computable
and unmeasured.

This module closes that loop in three parts:

1. **Recording** happens at the provider adapter, where token usage actually
   exists, through a module-level buffer (`record`). The `Provider.chat`
   contract still returns `str` — threading a usage object through every call
   site would touch the writers, the critics, the implementer, and the
   verifier for no gain, and the adapter is already where retries and
   empty-response diagnostics live.
2. **Persisting** is an explicit `flush(repo_dir)` at points that know the
   workspace (the review graph's post node, the build loop between tasks).
   Append-only JSONL, one line per call, so a crash loses at most the
   in-flight buffer rather than the month.
3. **Gating** is `cost_gate`, which reads the current month and refuses to
   start new work once the operator's cap is spent.

Two honesty rules the gate keeps, both inherited from `month_spend`:

- an unpriced call is never counted as zero. If any call in the month had no
  price in `.mas/cost-model.yaml`, the total is reported as a FLOOR and the
  unpriced count travels with it. A cap compared against a total that hides
  unpriced calls is a cap that silently stops working when you change models.
- no cap configured means no gating. `monthly_cap_usd: 0` is the default and
  means "not configured", stated rather than silently permissive — the gate
  says so instead of pretending it checked.

The cap blocks rather than warns, but only once a human has set one: the
operator opts in by writing a number, and the message says exactly how to
raise it. Agentic workflows burn 5-30x the tokens of a chat call, mostly on
re-sent context in tool loops, so an unbounded loop is a spend incident, not
a budgeting inconvenience.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import threading

from pydantic import BaseModel, Field

from ai_venture_studio.observability import (
    CostModel,
    CostRecord,
    estimate_cost,
    load_cost_model,
    month_spend,
)

LEDGER_FILE = "spend.jsonl"

# Calls recorded but not yet written. Guarded because voters run in a
# ThreadPoolExecutor — an unsynchronized list here would drop rows under the
# exact conditions that cost the most.
_buffer: list[dict] = []
_lock = threading.Lock()


class SpendEntry(BaseModel):
    at: str  # ISO8601 UTC
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    stage: str = ""  # review | build | product | ... , for attribution


class CostGateResult(BaseModel):
    passed: bool
    configured: bool  # False = no cap set; the gate did not check anything
    month: str = ""
    spent_usd: float = 0.0
    cap_usd: float = 0.0
    unpriced_calls: int = 0
    reasons: list[str] = Field(default_factory=list)
    note: str = ""

    @property
    def is_floor(self) -> bool:
        """True when unpriced calls mean `spent_usd` understates the truth."""
        return self.unpriced_calls > 0


def record(
    model: str, input_tokens: int | None, output_tokens: int | None,
    *, stage: str = "",
) -> None:
    """Buffer one provider call. Never raises: a metering failure must not
    take down the work being metered."""
    try:
        entry = SpendEntry(
            at=dt.datetime.now(dt.UTC).isoformat(),
            model=str(model),
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            stage=stage,
        )
    except (TypeError, ValueError):
        return
    with _lock:
        _buffer.append(entry.model_dump())


def buffered() -> int:
    with _lock:
        return len(_buffer)


def flush(repo_dir: str | pathlib.Path) -> int:
    """Append the buffer to the workspace ledger; returns rows written.

    Called where the workspace is known. The buffer is drained under the lock
    before any I/O so a concurrent record() lands in the next flush rather
    than being lost to a partial write.
    """
    with _lock:
        pending, _buffer[:] = list(_buffer), []
    if not pending:
        return 0
    path = pathlib.Path(repo_dir) / ".mas" / LEDGER_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in pending:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(pending)


def read_entries(
    repo_dir: str | pathlib.Path, *, month: str | None = None,
    since: str | None = None,
) -> list[SpendEntry]:
    """Ledger rows, optionally limited to a YYYY-MM month or an ISO instant.

    `since` is what makes "what did THIS run cost" answerable without
    threading attribution through every call site: a caller notes the time
    before it starts and asks afterwards.

    An unreadable row is skipped rather than fatal — a truncated last line
    from a killed process must not make the whole month unreadable.
    """
    path = pathlib.Path(repo_dir) / ".mas" / LEDGER_FILE
    if not path.exists():
        return []
    entries: list[SpendEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = SpendEntry(**json.loads(line))
        except Exception:  # noqa: BLE001 — a bad row is skipped, not fatal
            continue
        if month and not entry.at.startswith(month):
            continue
        if since and entry.at < since:
            continue
        entries.append(entry)
    return entries


class SpendSummary(BaseModel):
    """What a run, a task, or a month cost — the transparency primitive.

    `usd` counts only what the price table could price. `unpriced_calls`
    travels with it and `is_floor` says so, because the honest answer to "what
    did this cost" is sometimes "at least this much, and here is what I could
    not price".
    """

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0
    unpriced_calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def is_floor(self) -> bool:
        return self.unpriced_calls > 0


def summarize(
    entries: list[SpendEntry], cost_model: CostModel | None = None
) -> SpendSummary:
    model = cost_model or CostModel()
    records = priced(entries, model)
    total, unpriced = month_spend(records)
    return SpendSummary(
        calls=len(entries),
        input_tokens=sum(e.input_tokens for e in entries),
        output_tokens=sum(e.output_tokens for e in entries),
        usd=total,
        unpriced_calls=unpriced,
    )


def by_model(
    entries: list[SpendEntry], cost_model: CostModel | None = None
) -> dict[str, SpendSummary]:
    """Per-model rollup — the engineer-facing view. Which seat cost what is
    the question that actually changes a decision (drop a model, cache more,
    shorten a loop)."""
    model = cost_model or CostModel()
    grouped: dict[str, list[SpendEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.model, []).append(entry)
    return {name: summarize(rows, model) for name, rows in sorted(grouped.items())}


def summarize_workspace(
    repo_dir: str | pathlib.Path, *, month: str | None = None,
    since: str | None = None,
) -> SpendSummary:
    """The convenience path: load the price table and roll up in one call."""
    cost_model = load_cost_model(pathlib.Path(repo_dir) / ".mas")
    entries = read_entries(repo_dir, month=month, since=since)
    return summarize(entries, cost_model)


def render_plain(summary: SpendSummary, *, what: str = "this run") -> str:
    """The founder-facing sentence.

    Answers the signal the launch PRD is built on — "how much will a typical
    month of builds cost me? I'm scared to leave autopilot running" — in the
    register that asked it: no token counts, no model names, and an explicit
    "at least" when the number is a floor rather than a total.
    """
    if not summary.calls:
        return f"{what}: nothing recorded yet."
    if summary.unpriced_calls and not summary.usd:
        return (
            f"{what}: {summary.calls} model call(s). No prices are configured, "
            "so the cost is unknown — add them to .mas/cost-model.yaml to see "
            "money instead of counts."
        )
    prefix = "at least " if summary.is_floor else ""
    line = f"{what}: {prefix}${summary.usd:.2f} across {summary.calls} model call(s)"
    if summary.unpriced_calls:
        line += (
            f" — {summary.unpriced_calls} call(s) had no price configured, so "
            "the real figure is higher"
        )
    return line + "."


def typical_and_projected(
    repo_dir: str | pathlib.Path, *, runs: int = 5
) -> dict:
    """What a run has typically cost, and what a month at that rate looks like.

    Deliberately reports the median rather than the mean: agentic spend has a
    fat tail (one runaway loop drags an average somewhere useless), and the
    honest answer to "what will this cost me" is the typical case with the
    worst case named beside it.

    Runs are inferred from gaps in the ledger's timestamps — no attribution is
    threaded through the call sites, so this works on ledgers written before
    anything knew to label them. A gap is stated as a heuristic, because it
    is one.
    """
    import statistics

    cost_model = load_cost_model(pathlib.Path(repo_dir) / ".mas")
    entries = read_entries(repo_dir)
    if not entries:
        return {"runs_seen": 0, "note": "no spend recorded yet"}

    gap = dt.timedelta(minutes=30)
    groups: list[list[SpendEntry]] = [[]]
    previous: dt.datetime | None = None
    for entry in sorted(entries, key=lambda e: e.at):
        try:
            at = dt.datetime.fromisoformat(entry.at)
        except ValueError:
            continue
        if previous is not None and at - previous > gap:
            groups.append([])
        groups[-1].append(entry)
        previous = at
    groups = [g for g in groups if g]
    costs = [summarize(g, cost_model).usd for g in groups]
    recent = costs[-runs:] if costs else []
    return {
        "runs_seen": len(groups),
        "typical_run_usd": round(statistics.median(recent), 4) if recent else 0.0,
        "worst_run_usd": round(max(costs), 4) if costs else 0.0,
        "month_to_date_usd": summarize_workspace(
            repo_dir, month=current_month()
        ).usd,
        "note": "runs inferred from 30-minute gaps in the ledger — a heuristic, "
                "not attribution; median not mean, because one runaway loop "
                "makes an average useless",
    }


def priced(
    entries: list[SpendEntry], cost_model: CostModel
) -> list[CostRecord]:
    return [
        estimate_cost(e.model, e.input_tokens, e.output_tokens, cost_model)
        for e in entries
    ]


def current_month() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m")


def cost_gate(
    repo_dir: str | pathlib.Path, *, month: str | None = None
) -> CostGateResult:
    """Refuse to start new work once the month's cap is spent.

    Pure reads — safe before any LLM call, which is the only place a cost
    gate is worth anything.
    """
    mas_dir = pathlib.Path(repo_dir) / ".mas"
    cost_model = load_cost_model(mas_dir)
    window = month or current_month()

    if not cost_model.monthly_cap_usd:
        return CostGateResult(
            passed=True, configured=False, month=window,
            note="no monthly_cap_usd in .mas/cost-model.yaml — nothing was "
                 "checked. Set one to make the cap real.",
        )

    entries = read_entries(repo_dir, month=window)
    total, unpriced = month_spend(priced(entries, cost_model))
    cap = cost_model.monthly_cap_usd
    result = CostGateResult(
        passed=total < cap, configured=True, month=window,
        spent_usd=total, cap_usd=cap, unpriced_calls=unpriced,
    )
    if unpriced:
        # Stated, never folded into the total: the number is a floor.
        result.note = (
            f"{unpriced} call(s) this month have no price in "
            "cost-model.yaml, so ${:.2f} is a FLOOR, not the total".format(total)
        )
    if not result.passed:
        # Framed as the operator's own standing decision, because that is what
        # it is: the cap is off by default and only exists because somebody
        # wrote a number. The framework never decides to spend (ADR-U20), and
        # it should not sound like it decided to stop either.
        result.reasons.append(
            f"month {window} spend ${total:.2f} has reached the ${cap:.2f} "
            "limit YOU set in .mas/cost-model.yaml, so this run stopped. "
            "Raise monthly_cap_usd to continue, or set it to 0 to run "
            "unlimited — it is your key and your budget."
        )
    return result
