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
    repo_dir: str | pathlib.Path, *, month: str | None = None
) -> list[SpendEntry]:
    """Ledger rows, optionally limited to a YYYY-MM month.

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
        entries.append(entry)
    return entries


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
        result.reasons.append(
            f"month {window} spend ${total:.2f} has reached the "
            f"${cap:.2f} cap — new work is refused. Raise "
            "monthly_cap_usd in .mas/cost-model.yaml, or wait for the month "
            "to roll over. Spending decisions stay human."
        )
    return result
