"""The spend ledger — visibility, never gating.

observability.py could already price a call and total a month — and none of
it was reachable, because nothing ever recorded a call: cost was computable
and unmeasured.

The honesty rule under test: an unpriced call is never counted as zero (the
total is reported as a floor). There is deliberately no cap and no gate —
billing limits live at the provider that does the billing (ADR-032), so
this module states and never refuses.
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


def _workspace(tmp_path, prices=None):
    root = tmp_path / "ws"
    (root / ".mas").mkdir(parents=True)
    if prices is not None:
        (root / ".mas" / "cost-model.yaml").write_text(
            yaml.safe_dump({"prices": prices})
        )
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


# --- the month report: a statement, never a verdict --------------------------


def test_month_report_states_the_month(tmp_path):
    root = _workspace(tmp_path, prices=SONNET)
    spend.record("claude-sonnet-5", 1_000_000, 100_000)  # $3 + $1.50
    spend.flush(root)
    report = spend.month_report(root)
    assert report.spent_usd == pytest.approx(4.5)
    assert report.calls == 1
    assert report.unpriced_calls == 0
    assert report.is_floor is False


def test_an_unpriced_call_is_never_counted_as_zero(tmp_path):
    """A total that hides unpriced calls understates — the number must say
    it is a floor."""
    root = _workspace(tmp_path, prices=SONNET)
    spend.record("claude-sonnet-5", 1_000_000, 0)  # $3, priced
    spend.record("gpt-5", 5_000_000, 500_000)      # no price at all
    spend.flush(root)
    report = spend.month_report(root)
    assert report.unpriced_calls == 1
    assert report.is_floor is True
    assert "FLOOR" in report.note
    assert report.spent_usd == pytest.approx(3.0)  # the priced part only


def test_spend_in_another_month_stays_in_its_month(tmp_path):
    root = _workspace(tmp_path, prices=SONNET)
    path = root / ".mas" / spend.LEDGER_FILE
    path.write_text(json.dumps({
        "at": "2020-01-01T00:00:00+00:00", "model": "claude-sonnet-5",
        "input_tokens": 10_000_000, "output_tokens": 10_000_000,
    }) + "\n")
    assert spend.month_report(root).spent_usd == 0.0


# --- nothing refuses over money (ADR-032) ------------------------------------


def test_a_build_never_refuses_over_money(tmp_path):
    """The cap existed briefly (v0.65–v0.66) and was removed as a recorded
    decision: billing limits live at the provider. A month of heavy spend
    must not stop a build."""
    import shutil

    if shutil.which("git") is None:
        pytest.skip("git not on PATH")

    from ai_venture_studio.upstream import init_workspace
    from ai_venture_studio.upstream.build import run_build

    root = init_workspace(tmp_path / "ws", "ws", "web")
    (root / ".mas" / "cost-model.yaml").write_text(
        yaml.safe_dump({"prices": SONNET})
    )
    spend.record("claude-sonnet-5", 100_000_000, 10_000_000)  # a huge month
    spend.flush(root)

    # The removed gate returned a money-refusal BuildResult BEFORE touching
    # the spec. Reaching the missing-spec error proves no money check ran.
    with pytest.raises(FileNotFoundError, match="spec"):
        run_build(root, "no-such-spec")


def test_gate_1_never_refuses_over_money(tmp_path):
    from ai_venture_studio.orchestrator.graph import dor_gate_node

    root = _workspace(tmp_path, prices=SONNET)
    spend.record("claude-sonnet-5", 100_000_000, 10_000_000)
    spend.flush(root)

    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
        "@@ -0,0 +1 @@\n+x = 1\n"
    )
    state = {"target": "HEAD", "diff": {"raw": diff}}
    result = dor_gate_node(state, repo_dir=str(root))
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
    # v0.67: back to a pure statement — the cap was removed (ADR-032),
    # the visibility stays.
    assert "What this cost" in page
    assert "$3.00" in page
    assert "your own API key" in page  # whose money it is, said plainly


def test_the_studio_shows_the_card_even_before_any_spend(tmp_path):
    """The card shows before the first dollar: "no spend yet" is itself an
    answer to "I'm scared to leave autopilot running" — and the empty state
    is where the founder learns the number will live."""
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
