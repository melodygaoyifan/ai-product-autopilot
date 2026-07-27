"""v0.47.0 — the bot playtest fleet (doc 17 §45.2, doc 27 §79).

Verified against REAL sessions of a real deterministic simulation
(benchmarks/botfleet/toy_sim.py) spawned as a subprocess, not against a
mocked stream — the fleet's job is to find what a running game does, and a
stub would prove nothing about that. Engine adapters (Unity, Unreal) remain
open: they are code that emits this protocol.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from ai_venture_studio.lanes.botfleet import (
    SOFTLOCK_TICKS,
    SessionEvent,
    detect,
    parse_session,
    run_fleet,
    run_session,
)
from ai_venture_studio.lanes.realtime import NETWORK_PROFILES

REPO = pathlib.Path(__file__).resolve().parents[1]
TOY_SIM = REPO / "benchmarks" / "botfleet" / "toy_sim.py"
SIM_CMD = [sys.executable, str(TOY_SIM)]


def _ticks(n: int, *, state="a1", pos=(0.0, 0.0), reachable=None, start=0):
    return [
        SessionEvent(t=start + i, kind="tick", state_hash=state,
                     pos=list(pos), reachable=reachable)
        for i in range(n)
    ]


# --- the protocol -------------------------------------------------------------


def test_parse_skips_malformed_lines_without_losing_the_session():
    """A crashing game truncates its last line; losing the whole session to
    that would hide the crash we came for."""
    stream = (
        '{"t": 0, "kind": "tick", "state_hash": "a1", "pos": [0, 0]}\n'
        "\n"
        "not json at all\n"
        '{"t": 1, "kind": "crash", "message": "boom"}\n'
        '{"t": 2, "kind": "tick", "pos": ['  # truncated mid-write
    )
    events = parse_session(stream)
    assert [e.kind for e in events] == ["tick", "crash"]
    assert events[1].message == "boom"


def test_parse_tolerates_an_empty_stream():
    assert parse_session("") == [] and parse_session(None) == []


# --- detectors ----------------------------------------------------------------


def test_softlock_fires_only_after_the_threshold():
    assert detect(_ticks(SOFTLOCK_TICKS - 1)) == []
    found = detect(_ticks(SOFTLOCK_TICKS))
    assert [a.kind for a in found] == ["softlock"]
    assert f"{SOFTLOCK_TICKS} ticks from t=0" in found[0].detail


def test_movement_resets_the_softlock_run():
    events = _ticks(20) + _ticks(20, pos=(1.0, 0.0), state="b2", start=20)
    assert detect(events) == []


def test_a_continuing_condition_is_one_finding_not_one_per_tick():
    """The first real fleet run over the toy sim produced 44 findings for a
    single escaping bot; a continuing condition must collapse."""
    events = [
        SessionEvent(t=i, kind="tick", state_hash=f"h{i}", pos=[20.0 + i, 0.0])
        for i in range(30)
    ]
    found = detect(events, bounds=10.0)
    assert len(found) == 1
    assert found[0].kind == "out_of_bounds"
    assert "first breach at t=0" in found[0].detail


def test_out_of_bounds_signature_names_the_axis_and_side_not_the_position():
    """Walking further out is the same bug; walking out the other side is a
    different one."""
    east = detect([SessionEvent(t=0, kind="tick", pos=[11.0, 0.0])], bounds=10.0)
    further = detect([SessionEvent(t=0, kind="tick", pos=[99.0, 0.0])], bounds=10.0)
    west = detect([SessionEvent(t=0, kind="tick", pos=[-11.0, 0.0])], bounds=10.0)
    down = detect([SessionEvent(t=0, kind="tick", pos=[0.0, -11.0])], bounds=10.0)
    assert east[0].signature == further[0].signature
    assert east[0].signature != west[0].signature
    assert east[0].signature != down[0].signature


def test_no_bounds_declared_means_no_out_of_bounds_check():
    assert detect([SessionEvent(t=0, kind="tick", pos=[999.0, 999.0])]) == []


def test_unreachable_regression_fires_when_the_frontier_shrinks():
    events = [
        SessionEvent(t=0, kind="tick", state_hash="a", pos=[0, 0], reachable=12),
        SessionEvent(t=1, kind="tick", state_hash="b", pos=[1, 0], reachable=14),
        SessionEvent(t=2, kind="tick", state_hash="c", pos=[2, 0], reachable=9),
    ]
    found = detect(events)
    assert [a.kind for a in found] == ["unreachable_regression"]
    assert "14 → 9" in found[0].detail


def test_a_growing_frontier_is_not_a_finding():
    events = [
        SessionEvent(t=i, kind="tick", state_hash=f"h{i}", pos=[i, 0],
                     reachable=10 + i)
        for i in range(5)
    ]
    assert detect(events) == []


def test_crash_and_error_signatures_collapse_varying_numbers():
    """'index 41 out of range' and 'index 7 out of range' are one bug."""
    a = detect([SessionEvent(t=1, kind="crash", message="IndexError: tile 41 bad")])
    b = detect([SessionEvent(t=9, kind="crash", message="IndexError: tile 7 bad")])
    assert a[0].signature == b[0].signature
    c = detect([SessionEvent(t=1, kind="error", message="null texture ref")])
    assert c[0].kind == "error" and c[0].signature.startswith("error:")


# --- real sessions of the real toy sim ---------------------------------------


def test_toy_sim_exists_and_is_the_protocol_reference():
    assert TOY_SIM.exists()
    source = TOY_SIM.read_text(encoding="utf-8")
    assert "AUTOPRODUCT_BOT_SEED" in source  # reproducibility contract
    assert '"tick"' in source or "kind=\"tick\"" in source


def test_a_clean_seed_runs_clean(tmp_path):
    result = run_session(SIM_CMD, seed=1, session_id="s1", cwd=REPO, bounds=10.0)
    assert result.exit_code == 0
    assert result.anomalies == []
    assert result.ticks == 60


@pytest.mark.parametrize(("seed", "kind"), [
    (5, "softlock"),      # walks into a corner and stops
    (7, "crash"),         # raises after a few ticks
    (11, "out_of_bounds"),  # marches out of the play area
])
def test_each_planted_bug_is_found_in_a_real_session(seed, kind):
    result = run_session(SIM_CMD, seed=seed, session_id=f"s{seed}", cwd=REPO,
                         bounds=10.0)
    assert kind in [a.kind for a in result.anomalies], result.anomalies


def test_the_seed_makes_a_finding_reproducible():
    """Same seed, same session, same anomalies — a bug the fleet found must
    be replayable by hand or it is not actionable."""
    first = run_session(SIM_CMD, seed=5, session_id="a", cwd=REPO, bounds=10.0)
    second = run_session(SIM_CMD, seed=5, session_id="b", cwd=REPO, bounds=10.0)
    assert [a.signature for a in first.anomalies] == [
        a.signature for a in second.anomalies
    ]


def test_a_nonzero_exit_without_a_crash_event_is_still_a_crash(tmp_path):
    script = tmp_path / "dies.py"
    script.write_text(
        'import sys; print(\'{"t":0,"kind":"tick","pos":[0,0]}\'); '
        'sys.stderr.write("segfault-ish"); sys.exit(3)\n'
    )
    result = run_session([sys.executable, str(script)], seed=1, session_id="s",
                         cwd=tmp_path)
    assert result.exit_code == 3
    assert [a.kind for a in result.anomalies] == ["crash"]
    assert "exit code 3" in result.anomalies[0].detail


def test_a_hung_session_is_a_crash_not_a_hang(tmp_path):
    script = tmp_path / "hangs.py"
    script.write_text("import time; time.sleep(30)\n")
    result = run_session([sys.executable, str(script)], seed=1, session_id="s",
                         cwd=tmp_path, timeout_s=1.0)
    assert result.note == "timed out"
    assert result.anomalies[0].signature == "crash:timeout"


def test_an_unstartable_command_is_reported_not_raised(tmp_path):
    result = run_session(["./definitely-not-here"], seed=1, session_id="s",
                         cwd=tmp_path)
    assert result.anomalies == [] and "could not start" in result.note


# --- the fleet ----------------------------------------------------------------


def test_fleet_dedupes_across_sessions_and_names_the_reproduction():
    report = run_fleet(SIM_CMD, cwd=REPO, sessions=12, bounds=10.0,
                       net_profiles=("wifi_poor", "mobile_4g"), workers=4)
    assert report.status == "findings"
    kinds = sorted(f["kind"] for f in report.findings)
    assert kinds == ["crash", "out_of_bounds", "softlock"]
    assert len(report.sessions) == 12
    softlock = next(f for f in report.findings if f["kind"] == "softlock")
    # Seeds 5 and 10 both softlock: one finding, two sessions.
    assert softlock["sessions"] == 2
    assert "AUTOPRODUCT_BOT_SEED=" in softlock["reproduce"]
    assert set(softlock["net_profiles"]) <= set(NETWORK_PROFILES)


def test_a_clean_fleet_says_what_it_did_not_check():
    """§45.1: the fleet finds crashes and stuck states. 'Fun' is the human
    playtest gate's question, and the report must not imply otherwise."""
    report = run_fleet(SIM_CMD, cwd=REPO, sessions=3, base_seed=1, bounds=10.0)
    assert report.status == "ok", report.findings
    assert "human playtest gate" in report.detail


def test_no_command_and_missing_binary_both_skip_visibly(tmp_path):
    empty = run_fleet([], cwd=tmp_path)
    assert empty.status == "skipped"
    assert "never counted as a clean overnight run" in empty.detail

    absent = run_fleet(["./no-such-game"], cwd=tmp_path)
    assert absent.status == "skipped" and "not executable here" in absent.detail


def test_an_undeclared_network_profile_is_an_error():
    report = run_fleet(SIM_CMD, cwd=REPO, sessions=1,
                       net_profiles=("dial_up_1997",))
    assert report.status == "error"
    assert "unknown network profile" in report.detail
    assert "wifi_poor" in report.detail  # says what IS declared


def test_sessions_are_spread_across_the_declared_profiles():
    report = run_fleet(SIM_CMD, cwd=REPO, sessions=6, base_seed=1, bounds=10.0,
                       net_profiles=NETWORK_PROFILES)
    used = {s.net_profile for s in report.sessions}
    assert used == set(NETWORK_PROFILES)


# --- the CLI ------------------------------------------------------------------


def test_cli_exits_1_on_findings_and_prints_reproductions():
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app

    result = CliRunner().invoke(app, [
        "botfleet", " ".join(SIM_CMD), "--repo-dir", str(REPO),
        "--sessions", "12", "--bounds", "10.0",
        "--net-profile", "wifi_poor,mobile_4g",
    ])
    assert result.exit_code == 1
    flat = " ".join(result.output.split())
    assert "findings" in flat
    assert "softlock" in flat and "crash" in flat
    assert "reproduce: AUTOPRODUCT_BOT_SEED=" in flat


def test_cli_exits_0_when_clean():
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app

    result = CliRunner().invoke(app, [
        "botfleet", " ".join(SIM_CMD), "--repo-dir", str(REPO),
        "--sessions", "3", "--seed", "1", "--bounds", "10.0",
    ])
    assert result.exit_code == 0
    assert "human playtest gate" in " ".join(result.output.split())
