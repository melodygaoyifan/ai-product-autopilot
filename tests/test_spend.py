"""The spend ledger and the cost gate.

observability.py could already price a call, total a month, and compare
against a cap — and none of it was reachable, because nothing ever recorded a
call. `cap_check` had no production caller and there was no ledger for it to
read: cost was computable and unmeasured.

The two honesty rules under test here are the ones that make a cap mean
something over time: an unpriced call is never counted as zero (the total is
reported as a floor), and no configured cap means the gate says it checked
nothing rather than silently passing.
"""

from __future__ import annotations

import json

import pytest
import yaml

from ai_venture_studio import spend
from ai_venture_studio.observability import CostModel, estimate_cost


@pytest.fixture(autouse=True)
def _clean_buffer():
    """The buffer is module state; a leaked row would cross tests."""
    with spend._lock:
        spend._buffer.clear()
    yield
    with spend._lock:
        spend._buffer.clear()


def _workspace(tmp_path, cap=None, prices=None):
    root = tmp_path / "ws"
    (root / ".mas").mkdir(parents=True)
    model = {}
    if cap is not None:
        model["monthly_cap_usd"] = cap
    if prices is not None:
        model["prices"] = prices
    if model:
        (root / ".mas" / "cost-model.yaml").write_text(yaml.safe_dump(model))
    return root


SONNET = {"claude-sonnet-5": {"input": 3.0, "output": 15.0}}


# --- recording and persistence ----------------------------------------------


def test_a_call_is_buffered_then_persisted(tmp_path):
    root = _workspace(tmp_path)
    spend.record("claude-sonnet-5", 1000, 500, stage="review")
    assert spend.buffered() == 1

    assert spend.flush(root) == 1
    assert spend.buffered() == 0, "flush did not drain the buffer"

    entries = spend.read_entries(root)
    assert len(entries) == 1
    assert entries[0].model == "claude-sonnet-5"
    assert entries[0].input_tokens == 1000
    assert entries[0].output_tokens == 500
    assert entries[0].stage == "review"
    assert entries[0].at.endswith("+00:00") or "T" in entries[0].at


def test_flushing_appends_rather_than_replacing(tmp_path):
    root = _workspace(tmp_path)
    spend.record("m", 1, 1)
    spend.flush(root)
    spend.record("m", 2, 2)
    spend.flush(root)
    assert len(spend.read_entries(root)) == 2


def test_flushing_an_empty_buffer_writes_nothing(tmp_path):
    root = _workspace(tmp_path)
    assert spend.flush(root) == 0
    assert spend.read_entries(root) == []


def test_recording_never_raises_on_bad_input(tmp_path):
    """A metering failure must not take down the work being metered."""
    spend.record("m", None, None)          # unknown usage
    spend.record("m", "not-a-number", 5)   # type: ignore[arg-type]
    assert spend.buffered() >= 1


def test_a_truncated_ledger_row_is_skipped_not_fatal(tmp_path):
    """A killed process can leave half a line; the month must stay readable."""
    root = _workspace(tmp_path)
    spend.record("m", 10, 10)
    spend.flush(root)
    path = root / ".mas" / spend.LEDGER_FILE
    path.write_text(path.read_text() + '{"at": "2026-07-01T00:00:00+00:0')
    assert len(spend.read_entries(root)) == 1


def test_entries_can_be_limited_to_one_month(tmp_path):
    root = _workspace(tmp_path)
    path = root / ".mas" / spend.LEDGER_FILE
    path.write_text("\n".join(json.dumps(row) for row in [
        {"at": "2026-06-15T00:00:00+00:00", "model": "m", "input_tokens": 1,
         "output_tokens": 1},
        {"at": "2026-07-15T00:00:00+00:00", "model": "m", "input_tokens": 2,
         "output_tokens": 2},
    ]) + "\n")
    assert len(spend.read_entries(root, month="2026-07")) == 1
    assert len(spend.read_entries(root)) == 2


def test_concurrent_recording_loses_nothing(tmp_path):
    """Voters run in a thread pool — an unsynchronized buffer would drop rows
    under exactly the conditions that cost the most."""
    import threading

    root = _workspace(tmp_path)
    threads = [
        threading.Thread(target=lambda: [spend.record("m", 1, 1) for _ in range(50)])
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert spend.flush(root) == 400
    assert len(spend.read_entries(root)) == 400


# --- the gate ----------------------------------------------------------------


def test_no_configured_cap_means_the_gate_says_it_checked_nothing(tmp_path):
    """Silently passing would let an operator believe a cap existed."""
    result = spend.cost_gate(_workspace(tmp_path))
    assert result.passed is True
    assert result.configured is False
    assert "no monthly_cap_usd" in result.note


def test_the_gate_passes_under_the_cap(tmp_path):
    root = _workspace(tmp_path, cap=100.0, prices=SONNET)
    spend.record("claude-sonnet-5", 1_000_000, 100_000)  # $3 + $1.50
    spend.flush(root)
    result = spend.cost_gate(root)
    assert result.passed is True
    assert result.configured is True
    assert result.spent_usd == pytest.approx(4.5)
    assert result.unpriced_calls == 0
    assert result.is_floor is False


def test_the_gate_refuses_once_the_cap_is_reached(tmp_path):
    root = _workspace(tmp_path, cap=5.0, prices=SONNET)
    for _ in range(2):
        spend.record("claude-sonnet-5", 1_000_000, 100_000)  # $4.50 each
    spend.flush(root)
    result = spend.cost_gate(root)
    assert result.passed is False
    assert result.reasons and "cap" in result.reasons[0]
    # the way out is named, and the limit is attributed to whoever set it
    assert "monthly_cap_usd" in result.reasons[0]
    assert "YOU set" in result.reasons[0]


def test_an_unpriced_call_is_never_counted_as_zero(tmp_path):
    """A cap compared against a total that hides unpriced calls silently stops
    working the day you switch models."""
    root = _workspace(tmp_path, cap=100.0, prices=SONNET)
    spend.record("claude-sonnet-5", 1_000_000, 0)  # $3, priced
    spend.record("gpt-5", 5_000_000, 500_000)      # no price at all
    spend.flush(root)
    result = spend.cost_gate(root)
    assert result.unpriced_calls == 1
    assert result.is_floor is True
    assert "FLOOR" in result.note
    assert result.spent_usd == pytest.approx(3.0)  # the priced part only


def test_spend_in_another_month_does_not_block_this_one(tmp_path):
    root = _workspace(tmp_path, cap=1.0, prices=SONNET)
    path = root / ".mas" / spend.LEDGER_FILE
    path.write_text(json.dumps({
        "at": "2020-01-01T00:00:00+00:00", "model": "claude-sonnet-5",
        "input_tokens": 10_000_000, "output_tokens": 10_000_000,
    }) + "\n")
    assert spend.cost_gate(root).passed is True


# --- the wiring: a cap nothing reads is not a cap ----------------------------


def test_a_build_refuses_when_the_cap_is_spent(tmp_path):
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git not on PATH")

    from ai_venture_studio.upstream.build import run_build

    root = _workspace(tmp_path, cap=1.0, prices=SONNET)
    spend.record("claude-sonnet-5", 1_000_000, 0)  # $3 > $1 cap
    spend.flush(root)

    result = run_build(root, "anything")
    assert result.status == "error"
    assert "cap" in result.detail


def test_gate_1_refuses_a_review_when_the_cap_is_spent(tmp_path):
    """The cap is only worth anything BEFORE the spend, which is what the
    Definition-of-Ready gate is for."""
    from ai_venture_studio.orchestrator.graph import dor_gate_node

    root = _workspace(tmp_path, cap=1.0, prices=SONNET)
    spend.record("claude-sonnet-5", 1_000_000, 0)
    spend.flush(root)

    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -0,0 +1 @@\n+x = 1\n"
    )
    state = {"target": "HEAD", "diff": {"raw": diff}}
    result = dor_gate_node(state, repo_dir=str(root))
    assert result["dor_pass"] is False
    assert any("cap" in reason for reason in result["dor_reasons"])


def test_gate_1_still_passes_a_normal_review_with_no_cap(tmp_path):
    from ai_venture_studio.orchestrator.graph import dor_gate_node

    root = _workspace(tmp_path)
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -0,0 +1 @@\n+x = 1\n"
    )
    result = dor_gate_node({"target": "HEAD", "diff": {"raw": diff}},
                           repo_dir=str(root))
    assert result["dor_pass"] is True


def test_pricing_matches_the_observability_model(tmp_path):
    """spend.priced must agree with estimate_cost, or the gate and the cost
    report would disagree about the same month."""
    entries_root = _workspace(tmp_path, prices=SONNET)
    spend.record("claude-sonnet-5", 1_000_000, 1_000_000)
    spend.flush(entries_root)
    entries = spend.read_entries(entries_root)
    model = CostModel(prices=SONNET)
    assert spend.priced(entries, model)[0].cost_usd == \
        estimate_cost("claude-sonnet-5", 1_000_000, 1_000_000, model).cost_usd


# --- transparency: the primary surface --------------------------------------
#
# The cap is opt-in and secondary. What the founder signal actually asked for
# was to SEE the number: "how much will a typical month of builds cost me?
# I'm scared to leave autopilot running."


def test_a_summary_reports_calls_tokens_and_money(tmp_path):
    root = _workspace(tmp_path, prices=SONNET)
    spend.record("claude-sonnet-5", 1_000_000, 100_000)  # $3.00 + $1.50
    spend.flush(root)
    summary = spend.summarize_workspace(root)
    assert summary.calls == 1
    assert summary.total_tokens == 1_100_000
    assert summary.usd == pytest.approx(4.5)
    assert summary.is_floor is False


def test_the_founder_line_says_at_least_when_the_number_is_a_floor(tmp_path):
    """Overstating certainty about someone's money is the failure mode here."""
    root = _workspace(tmp_path, prices=SONNET)
    spend.record("claude-sonnet-5", 1_000_000, 0)
    spend.record("gpt-5", 500_000, 50_000)  # unpriced
    spend.flush(root)
    line = spend.render_plain(spend.summarize_workspace(root), what="This build")
    assert "at least $3.00" in line
    assert "no price configured" in line
    assert "higher" in line


def test_the_founder_line_is_plain_when_everything_is_priced(tmp_path):
    root = _workspace(tmp_path, prices=SONNET)
    spend.record("claude-sonnet-5", 1_000_000, 0)
    spend.flush(root)
    line = spend.render_plain(spend.summarize_workspace(root), what="This build")
    assert line == "This build: $3.00 across 1 model call(s)."
    assert "token" not in line.lower()  # founder register: no token counts


def test_with_no_prices_configured_it_says_unknown_rather_than_zero(tmp_path):
    """"$0.00" would be a lie; "unknown, here's how to fix it" is not."""
    root = _workspace(tmp_path)  # no price table at all
    spend.record("claude-sonnet-5", 1_000_000, 0)
    spend.flush(root)
    line = spend.render_plain(spend.summarize_workspace(root))
    assert "unknown" in line
    assert "cost-model.yaml" in line
    assert "$0.00" not in line


def test_nothing_recorded_says_so(tmp_path):
    assert "nothing recorded" in spend.render_plain(
        spend.summarize_workspace(_workspace(tmp_path))
    )


def test_per_model_rollup_answers_which_seat_cost_what(tmp_path):
    root = _workspace(tmp_path, prices=SONNET)
    spend.record("claude-sonnet-5", 1_000_000, 0)
    spend.record("claude-sonnet-5", 1_000_000, 0)
    spend.record("gpt-5", 10, 10)
    spend.flush(root)
    rollup = spend.by_model(
        spend.read_entries(root), spend.load_cost_model(root / ".mas")
    )
    assert rollup["claude-sonnet-5"].calls == 2
    assert rollup["claude-sonnet-5"].usd == pytest.approx(6.0)
    assert rollup["gpt-5"].unpriced_calls == 1


def test_since_answers_what_this_run_cost(tmp_path):
    """Attribution without threading a label through every call site: note the
    time, ask afterwards."""
    import datetime as dt
    import json as _json

    root = _workspace(tmp_path, prices=SONNET)
    path = root / ".mas" / spend.LEDGER_FILE
    early = dt.datetime(2026, 7, 29, 9, 0, tzinfo=dt.UTC)
    late = dt.datetime(2026, 7, 29, 12, 0, tzinfo=dt.UTC)
    path.write_text("\n".join(_json.dumps(row) for row in [
        {"at": early.isoformat(), "model": "claude-sonnet-5",
         "input_tokens": 1_000_000, "output_tokens": 0},
        {"at": late.isoformat(), "model": "claude-sonnet-5",
         "input_tokens": 2_000_000, "output_tokens": 0},
    ]) + "\n")
    this_run = spend.summarize_workspace(root, since=late.isoformat())
    assert this_run.calls == 1
    assert this_run.usd == pytest.approx(6.0)


def test_typical_uses_the_median_and_names_the_worst_case(tmp_path):
    """Agentic spend has a fat tail — one runaway loop makes an average
    useless, so the typical case and the worst case are reported separately."""
    import datetime as dt
    import json as _json

    root = _workspace(tmp_path, prices=SONNET)
    base = dt.datetime(2026, 7, 29, 8, 0, tzinfo=dt.UTC)
    rows = []
    # three cheap runs, then one expensive one, each separated by hours
    for run, tokens in enumerate([1_000_000, 1_000_000, 1_000_000, 9_000_000]):
        rows.append({
            "at": (base + dt.timedelta(hours=run * 3)).isoformat(),
            "model": "claude-sonnet-5",
            "input_tokens": tokens, "output_tokens": 0,
        })
    (root / ".mas" / spend.LEDGER_FILE).write_text(
        "\n".join(_json.dumps(r) for r in rows) + "\n"
    )
    shape = spend.typical_and_projected(root)
    assert shape["runs_seen"] == 4
    assert shape["typical_run_usd"] == pytest.approx(3.0)   # median, not mean
    assert shape["worst_run_usd"] == pytest.approx(27.0)    # named separately
    assert "heuristic" in shape["note"]  # the run-splitting is stated as one


def test_typical_on_an_empty_ledger_does_not_invent_a_number(tmp_path):
    shape = spend.typical_and_projected(_workspace(tmp_path))
    assert shape["runs_seen"] == 0
    assert "no spend recorded" in shape["note"]


def test_the_cap_message_reads_as_the_operators_own_limit(tmp_path):
    """The framework never decides to spend (ADR-U20); it should not sound
    like it decided to stop either. The cap is off by default and only exists
    because somebody wrote a number."""
    root = _workspace(tmp_path, cap=1.0, prices=SONNET)
    spend.record("claude-sonnet-5", 1_000_000, 0)
    spend.flush(root)
    reason = spend.cost_gate(root).reasons[0]
    assert "YOU set" in reason
    assert "your key and your budget" in reason


# --- cost reaches the surfaces people actually look at ----------------------


def test_the_studio_product_page_shows_what_it_cost(tmp_path):
    """A number you have to know to go looking for does not answer "I'm
    scared to leave autopilot running"."""
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git not on PATH")
    from fastapi.testclient import TestClient

    from ai_venture_studio.studio import create_studio_app
    from ai_venture_studio.upstream import init_workspace

    root = init_workspace(tmp_path / "prod", "prod", "web")
    (root / ".mas" / "cost-model.yaml").write_text(yaml.safe_dump({"prices": SONNET}))
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "BUILD-REPORT.md").write_text("# done", encoding="utf-8")
    spend.record("claude-sonnet-5", 1_000_000, 0)  # $3.00
    spend.flush(root)

    page = TestClient(
        create_studio_app(root, spawn=lambda r: 1, provider="mock")
    ).get("/").text
    # v0.66: the cost card grew a ceiling and became the spend guard —
    # same page, same money, now with the cap state beside it.
    assert "Spending &amp; cap" in page
    assert "$3.00" in page
    assert "your own API key" in page  # whose money it is, said plainly


def test_the_studio_shows_the_guard_even_before_any_spend(tmp_path):
    """The old card hid itself until money had been spent — which is
    exactly backwards for the cap: the ceiling matters BEFORE the first
    dollar, not after (v0.66 spend guard; the set-cap suggestion is the
    point of the empty state)."""
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git not on PATH")
    from fastapi.testclient import TestClient

    from ai_venture_studio.studio import create_studio_app
    from ai_venture_studio.upstream import init_workspace

    root = init_workspace(tmp_path / "quiet", "quiet", "web")
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "BUILD-REPORT.md").write_text("# done", encoding="utf-8")
    page = TestClient(
        create_studio_app(root, spawn=lambda r: 1, provider="mock")
    ).get("/").text
    assert "No model calls yet this month" in page
    assert "action=/cap" in page


def test_the_build_report_gets_a_cost_section(tmp_path):
    """Appended as arithmetic, never prompted — the number must not be model
    prose."""
    root = _workspace(tmp_path, prices=SONNET)
    (root / "product").mkdir(parents=True, exist_ok=True)
    spend.record("claude-sonnet-5", 1_000_000, 0)
    spend.flush(root)

    summary = spend.summarize_workspace(root)
    line = spend.render_plain(summary, what="This build")
    assert "$3.00" in line
    # the section the autopilot appends is built from exactly this line
    assert line.startswith("This build: $3.00")
