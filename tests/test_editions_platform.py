"""Docs 24-25: editions (narrowing-only, invariant 14.21), the no-key demo
replay (rung R1), opt-in telemetry (ADR-U28), and the platform's own
claims checked by its own linter (ADR-U29) — in this suite, which is the CI.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from autoproduct.cli import app
from autoproduct.editions import (
    EDITIONS,
    EditionError,
    edition_lint,
    load_edition_preset,
    resolve_edition,
)
from autoproduct.product import lint_ledger
from autoproduct.product.platform_claims import check_platform_claims, check_repo
from autoproduct.usage_telemetry import (
    PAYLOAD_FIELDS,
    build_payload,
    set_telemetry,
    telemetry_enabled,
)

REPO = Path(__file__).parent.parent
runner = CliRunner()


# --- editions (doc 24, invariant 14.21) ---------------------------------------


def test_all_three_presets_lint_clean_and_resolve(tmp_path):
    for name in EDITIONS:
        raw = load_edition_preset(name)
        assert raw["edition"] == name
        target = resolve_edition(tmp_path / name, name)
        assert target.exists()
        entry = REPO / raw["docs_entry"]
        assert entry.exists(), f"{name}: docs_entry {raw['docs_entry']} missing"


def _solo() -> dict:
    return yaml.safe_load((REPO / "editions" / "solo" / "edition.yaml").read_text())


def test_edition_lint_refuses_widening():
    widened = _solo()
    widened["skip_stages"] = ["deploy_review"]
    assert any("widen" in f for f in edition_lint(widened))

    raised = _solo()
    raised["defaults"]["cadence_ceilings"] = {"content_geo": "9/week"}
    assert any("never be raised" in f or "never raised" in f
               for f in edition_lint(raised))

    dropped = _solo()
    dropped["gate_policy"]["never_consolidate"] = ["PL5"]
    assert any("floor" in f for f in edition_lint(dropped))

    unknown = _solo()
    unknown["trust_mode"] = True
    assert any("unknown" in f for f in edition_lint(unknown))

    unowned = _solo()
    unowned["defaults"]["substrate_rung"] = "S3"
    assert any("require_gate_owner" in f for f in edition_lint(unowned))


def test_init_edition_cli(tmp_path):
    ws = tmp_path / "solo-ws"
    result = runner.invoke(app, [
        "init", str(ws), "--profile", "web", "--edition", "solo",
    ])
    assert result.exit_code == 0, result.output
    resolved = yaml.safe_load((ws / ".mas" / "edition.yaml").read_text())
    assert resolved["edition"] == "solo"
    assert resolved["defaults"]["wip_limit"] == 1

    refused = runner.invoke(app, [
        "init", str(tmp_path / "ent-ws"), "--profile", "web",
        "--edition", "enterprise",
    ])
    assert refused.exit_code == 2  # no --gate-owner: the 12% profile, enforced
    assert "gate-owner" in refused.output

    owned = runner.invoke(app, [
        "init", str(tmp_path / "ent-ws2"), "--profile", "web",
        "--edition", "enterprise", "--gate-owner", "melody",
    ])
    assert owned.exit_code == 0, owned.output
    resolved = yaml.safe_load(
        (tmp_path / "ent-ws2" / ".mas" / "edition.yaml").read_text()
    )
    assert resolved["gate_policy"]["gate_owner"] == "melody"


def test_init_from_bench_seeds_the_fixture_fdr(tmp_path):
    ws = tmp_path / "demo-ws"
    result = runner.invoke(app, [
        "init", str(ws), "--profile", "web", "--from-bench", "01-groupbuy-api",
    ])
    assert result.exit_code == 0, result.output
    assert "团购" in (ws / "FDR.md").read_text()  # the real bench FDR, verbatim


# --- rung R1: the no-key demo replay (doc 25 §73.1) -----------------------------


def test_replay_demo_runs_offline():
    result = runner.invoke(app, ["replay", "--demo"])
    assert result.exit_code == 0, result.output
    out = " ".join(result.output.split())
    assert "offline demo bundle" in out
    assert "verdict:" in out and "ESCALATE_TOOL_FAILURE" in out  # honest demo
    assert "vote" in out  # the timeline rendered


def test_demo_bundle_is_redacted():
    bundle = REPO / "editions" / "demo" / "reviews"
    text = "".join(p.read_text() for p in bundle.rglob("*.yaml"))
    assert "/Users/" not in text
    assert "sk-" not in text and "AKIA" not in text


# --- telemetry (ADR-U28) ---------------------------------------------------------


def test_telemetry_default_off_and_payload_schema_pinned(tmp_path):
    assert not telemetry_enabled(tmp_path)  # default off, no file needed
    payload = build_payload(tmp_path)
    assert tuple(sorted(payload)) == tuple(sorted(PAYLOAD_FIELDS))
    blob = json.dumps(payload)
    for forbidden in ("fdr", "prompt", "claim", "repo_name", "code"):
        assert forbidden not in blob.lower().replace("error_classes", "")
    set_telemetry(tmp_path, True)
    assert telemetry_enabled(tmp_path)
    set_telemetry(tmp_path, False)
    assert not telemetry_enabled(tmp_path)


def test_telemetry_cli_show(tmp_path):
    result = runner.invoke(app, ["telemetry", "show", "--workspace", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.output[: result.output.rindex("}") + 1])
    assert payload["schema_version"] == 1
    assert "nothing is sent" in " ".join(result.output.split())


# --- ADR-U29: the platform's claims pass its own linter, here, in CI ---------------


def test_platform_ledger_passes_claim_lint():
    ledger = yaml.safe_load((REPO / "claims" / "platform.yaml").read_text())
    assert lint_ledger(ledger, "launch", today=dt.date(2026, 7, 26)) == []


def test_readme_and_benchmark_page_resolve_against_the_ledger():
    findings = check_repo(REPO)
    assert findings == [], [f.model_dump() for f in findings]


def test_asserting_beyond_the_ledger_fails():
    ledger = yaml.safe_load((REPO / "claims" / "platform.yaml").read_text())
    doctored = "Our benchmark shows 99.9% recall on every workload."
    findings = check_platform_claims(doctored, ledger)
    assert [f.rule for f in findings] == ["uncovered_number"]

    superlative = "The fastest agent framework available."
    findings = check_platform_claims(superlative, ledger)
    assert "unmeasured_superlative" in {f.rule for f in findings}

    fine = "A named cheapest test (a stub behind a click counter)."
    assert check_platform_claims(fine, ledger) == []  # term of art, exempt
