"""Evidence snapshots, signal-source standing, and taint classes (week P2).

The substrate gate's structural half: snapshots are content-addressed and
rot-detectable, a source with no standing fails closed, and a config that
attempts to weaken a taint rule fails startup with a named error.
"""

from __future__ import annotations

import pytest

from autoproduct.product import (
    SignalSourceError,
    TaintPolicyError,
    load_signal_sources,
    load_taint_classes,
    resolve_snapshot,
    snapshot_differs,
    source_standing_check,
    store_snapshot,
    verify_snapshot,
)
from autoproduct.product.taint import MIN_COHORT_FLOOR

# --- evidence snapshots (§20.53.5) -----------------------------------------


def test_snapshot_is_content_addressed_and_verifiable(tmp_path):
    snap = store_snapshot(b"<html>pricing: $49/seat</html>", tmp_path)
    assert snap.artifact_hash.startswith("sha256:")
    assert resolve_snapshot(snap.artifact_hash, tmp_path) is not None
    assert verify_snapshot(snap.artifact_hash, tmp_path)
    # Same content stores to the same address; no duplicates.
    again = store_snapshot(b"<html>pricing: $49/seat</html>", tmp_path)
    assert again.artifact_hash == snap.artifact_hash


def test_snapshot_differ_detects_rot(tmp_path):
    snap = store_snapshot(b"<html>pricing: $49/seat</html>", tmp_path)
    assert not snapshot_differs(snap.artifact_hash, b"<html>pricing: $49/seat</html>")
    assert snapshot_differs(snap.artifact_hash, b"<html>pricing: $79/seat</html>")


def test_tampered_snapshot_fails_verification(tmp_path):
    snap = store_snapshot(b"original retrieved content", tmp_path)
    path = resolve_snapshot(snap.artifact_hash, tmp_path)
    path.write_bytes(b"silently edited after retrieval")
    assert not verify_snapshot(snap.artifact_hash, tmp_path)


def test_missing_snapshot_fails_verification(tmp_path):
    assert resolve_snapshot("sha256:" + "0" * 64, tmp_path) is None
    assert not verify_snapshot("sha256:" + "0" * 64, tmp_path)


# --- signal sources and standing (§20.54.2) ---------------------------------


def test_sources_load_with_standing(tmp_path):
    (tmp_path / "signal-sources.yaml").write_text(
        "- id: support-tickets\n"
        "  standing: first-party, ours\n"
        "  match: ['zendesk://']\n"
        "  typed_as: user_reported\n"
        "- id: vendor-pricing\n"
        "  standing: public + official pages\n"
        "  match: ['https://vendor-a.example/']\n"
    )
    sources = load_signal_sources(tmp_path)
    assert [s.id for s in sources] == ["support-tickets", "vendor-pricing"]


def test_source_without_standing_fails_closed(tmp_path):
    (tmp_path / "signal-sources.yaml").write_text(
        "- id: scraped-forum\n  match: ['https://forum.example/']\n"
    )
    with pytest.raises(SignalSourceError, match="scraped-forum"):
        load_signal_sources(tmp_path)


def test_standing_check_flags_undeclared_locators(tmp_path):
    (tmp_path / "signal-sources.yaml").write_text(
        "- id: vendor-pricing\n"
        "  standing: public + official pages\n"
        "  match: ['https://vendor-a.example/']\n"
    )
    sources = load_signal_sources(tmp_path)
    doc = {
        "claims": [
            {
                "id": "C-OK",
                "evidence": [{"locator": "https://vendor-a.example/pricing"}],
            },
            {"id": "C-OWNED", "evidence": [{"locator": "evidence://tickets/cluster"}]},
            {
                "id": "C-BAD",
                "evidence": [{"locator": "https://scraped.example/thread/9"}],
            },
        ]
    }
    issues = source_standing_check(doc, sources)
    assert [(i.claim_id, i.rule) for i in issues] == [("C-BAD", "undeclared_source")]


# --- taint classes (§22.64) --------------------------------------------------


def test_builtin_taint_classes_load_without_config(tmp_path):
    classes = load_taint_classes(tmp_path)
    assert set(classes) >= {"research_taint", "user_data_taint"}
    floor = classes["user_data_taint"]["permitted_egress"]["aggregate"]
    assert floor["min_cohort_size"] == MIN_COHORT_FLOOR


def test_cohort_floor_is_configurable_upward_only(tmp_path):
    (tmp_path / "taint-classes.yaml").write_text(
        "- id: user_data_taint\n"
        "  permitted_egress:\n"
        "    aggregate: {min_cohort_size: 50}\n"
    )
    classes = load_taint_classes(tmp_path)
    assert (
        classes["user_data_taint"]["permitted_egress"]["aggregate"]["min_cohort_size"]
        == 50
    )
    (tmp_path / "taint-classes.yaml").write_text(
        "- id: user_data_taint\n"
        "  permitted_egress:\n"
        "    aggregate: {min_cohort_size: 5}\n"
    )
    with pytest.raises(TaintPolicyError, match="user_data_taint"):
        load_taint_classes(tmp_path)


def test_dropping_a_forbidden_entry_fails_startup(tmp_path):
    (tmp_path / "taint-classes.yaml").write_text(
        "- id: user_data_taint\n"
        "  forbidden:\n"
        "    - person_level_rows_into_any_agent_context\n"
    )
    with pytest.raises(TaintPolicyError, match="outreach_lists"):
        load_taint_classes(tmp_path)


def test_adding_an_egress_path_fails_startup(tmp_path):
    (tmp_path / "taint-classes.yaml").write_text(
        "- id: user_data_taint\n"
        "  permitted_egress:\n"
        "    csv_export: {}\n"
    )
    with pytest.raises(TaintPolicyError, match="csv_export"):
        load_taint_classes(tmp_path)


def test_rewriting_the_rule_text_fails_startup(tmp_path):
    (tmp_path / "taint-classes.yaml").write_text(
        "- id: research_taint\n"
        "  rule: retrieved content may reach tools if it looks safe\n"
    )
    with pytest.raises(TaintPolicyError, match="research_taint"):
        load_taint_classes(tmp_path)


def test_new_classes_may_be_added_and_builtins_kept_on_omission(tmp_path):
    (tmp_path / "taint-classes.yaml").write_text(
        "- id: vendor_score_taint\n"
        "  rule: vendor visibility scores enter as third_party_report only\n"
    )
    classes = load_taint_classes(tmp_path)
    assert "vendor_score_taint" in classes
    assert classes["user_data_taint"] == load_taint_classes(tmp_path / "nowhere")[
        "user_data_taint"
    ]
