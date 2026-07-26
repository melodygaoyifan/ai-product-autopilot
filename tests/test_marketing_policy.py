"""The P3 autonomy ceiling, channel profiles, compliance expiry, Gate PL3.

The structural half of the v2.2.0 gate: forbidden_autonomous additions are
loader-enforced and a config cannot grant publish_external (startup-tested);
a channel profile cannot weaken a core check or raise a cadence ceiling;
the compliance ruleset fails closed on expiry; approvals have no unscoped
representation.
"""

from __future__ import annotations

import datetime as dt

import pytest

from autoproduct.marketing import (
    FORBIDDEN_AUTONOMOUS,
    ApprovalScope,
    AutonomyPolicyError,
    ChannelProfileError,
    ComplianceProfileError,
    DeliverabilityConfigError,
    Draft,
    GateBlockedError,
    RegisteredClaim,
    ReleaseContract,
    ReleaseContractError,
    artifact_hash,
    assemble_gate_packet,
    load_channel_profiles,
    load_compliance_profile,
    load_deliverability_config,
    load_forbidden_autonomous,
    load_release_contract,
    record_approval,
)

TODAY = dt.date(2026, 7, 26)


# --- forbidden_autonomous (§21.57.2, ADR-U19/U20) ---------------------------


def test_floor_contains_the_p3_additions(tmp_path):
    effective = load_forbidden_autonomous(tmp_path)
    assert {
        "publish_external",
        "send_outbound",
        "spend_money",
        "contact_list_construction",
        "platform_submission",
    } <= effective
    assert effective == FORBIDDEN_AUTONOMOUS


def test_config_may_narrow_autonomy(tmp_path):
    (tmp_path / "authoring-policy.yaml").write_text(
        "forbidden_autonomous_add: [update_status_page]\n"
    )
    effective = load_forbidden_autonomous(tmp_path)
    assert "update_status_page" in effective
    assert FORBIDDEN_AUTONOMOUS <= effective


def test_config_cannot_grant_publish_external(tmp_path):
    # The startup test of §23 week P5: a config attempting to widen autonomy
    # fails before anything runs, whatever key shape it tries.
    (tmp_path / "authoring-policy.yaml").write_text(
        "allow_autonomous: [publish_external]\n"
    )
    with pytest.raises(AutonomyPolicyError, match="never widen"):
        load_forbidden_autonomous(tmp_path)
    (tmp_path / "authoring-policy.yaml").write_text(
        "forbidden_autonomous_remove: [spend_money]\n"
    )
    with pytest.raises(AutonomyPolicyError):
        load_forbidden_autonomous(tmp_path)


# --- channel profiles (§21.59, ADR-U12/U20) ---------------------------------


def test_builtin_channels_load_and_paid_does_not_exist(tmp_path):
    channels = load_channel_profiles(tmp_path)
    assert set(channels) == {
        "content_geo",
        "email",
        "community",
        "social",
        "product_surface",
    }
    assert "claim_substantiation_check" in channels["content_geo"].det_tools


def test_profile_may_add_and_lower_never_remove_or_raise(tmp_path):
    (tmp_path / "channel-profile.yaml").write_text(
        "channels:\n"
        "  - id: content_geo\n"
        "    det_tools_add: [disclosure_lint]\n"
        "    cadence: {max_publishes_per_week: 1}\n"
    )
    channels = load_channel_profiles(tmp_path)
    assert "disclosure_lint" in channels["content_geo"].det_tools
    assert "spam_policy_check" in channels["content_geo"].det_tools  # core kept
    assert channels["content_geo"].cadence["max_publishes_per_week"] == 1

    (tmp_path / "channel-profile.yaml").write_text(
        "channels:\n"
        "  - id: content_geo\n"
        "    cadence: {max_publishes_per_week: 50}\n"
    )
    with pytest.raises(ChannelProfileError, match="never raised"):
        load_channel_profiles(tmp_path)

    (tmp_path / "channel-profile.yaml").write_text(
        "channels:\n"
        "  - id: content_geo\n"
        "    det_tools: [brand_and_safety_scan]\n"
    )
    with pytest.raises(ChannelProfileError, match="core set"):
        load_channel_profiles(tmp_path)


def test_paid_channel_is_rejected_by_name(tmp_path):
    (tmp_path / "channel-profile.yaml").write_text(
        "channels:\n  - id: paid\n    cadence: {max_campaigns_per_week: 1}\n"
    )
    with pytest.raises(ChannelProfileError, match="ADR-U20"):
        load_channel_profiles(tmp_path)


# --- compliance profile expiry (risk R-P4) ----------------------------------


def test_compliance_profile_fails_closed_on_expiry(tmp_path):
    (tmp_path / "compliance-profile.yaml").write_text(
        "verified_on: '2026-01-05'\nreview_cadence_days: 90\n"
    )
    with pytest.raises(ComplianceProfileError, match="expired"):
        load_compliance_profile(tmp_path, today=TODAY)
    (tmp_path / "compliance-profile.yaml").write_text(
        "verified_on: '2026-07-01'\nreview_cadence_days: 90\n"
    )
    assert load_compliance_profile(tmp_path, today=TODAY).verified_on == "2026-07-01"


def test_compliance_profile_requires_verified_on(tmp_path):
    (tmp_path / "compliance-profile.yaml").write_text("review_cadence_days: 90\n")
    with pytest.raises(ComplianceProfileError, match="verified_on"):
        load_compliance_profile(tmp_path, today=TODAY)


def test_deliverability_config_cannot_touch_consent_or_suppression(tmp_path):
    (tmp_path / "deliverability.yaml").write_text("consent_required: false\n")
    with pytest.raises(DeliverabilityConfigError, match="non-overridable"):
        load_deliverability_config(tmp_path)
    (tmp_path / "deliverability.yaml").write_text("skip_suppression_check: true\n")
    with pytest.raises(DeliverabilityConfigError):
        load_deliverability_config(tmp_path)
    (tmp_path / "deliverability.yaml").write_text("bounce_rate_ceiling: 0.01\n")
    assert load_deliverability_config(tmp_path).bounce_rate_ceiling == 0.01


# --- release contract (§21.57.4) ---------------------------------------------


def test_release_contract_roundtrip(tmp_path):
    path = tmp_path / "release_to_p3.yaml"
    path.write_text(
        "release:\n"
        "  prd_ref: PRD-2026-014\n"
        "  instrumentation_verified: true\n"
        "  claims_available:\n"
        "    - {id: C-101, text: 'exports 12,000 rows in under 4 seconds',\n"
        "       source_type: primary_measured}\n"
    )
    contract = load_release_contract(path)
    assert contract.claim("C-101").source_type == "primary_measured"
    assert contract.claim("C-999") is None

    path.write_text("not a mapping")
    with pytest.raises(ReleaseContractError):
        load_release_contract(path)


# --- Gate PL3 (§21.61.5) ------------------------------------------------------


def _register() -> ReleaseContract:
    return ReleaseContract(
        prd_ref="PRD-2026-014",
        instrumentation_verified=True,
        claims_available=[
            RegisteredClaim(
                id="C-101",
                text="exports 12,000 rows in under 4 seconds",
                source_type="primary_measured",
                evidence=[{"method": "benchmark_run", "locator": "bench://july"}],
            )
        ],
    )


def _draft() -> Draft:
    return Draft(
        id="post-1",
        channel="content_geo",
        text="autoproduct exports 12,000 rows in under 4 seconds.",
    )


def test_gate_packet_requires_green_backstops_and_instrumentation():
    with pytest.raises(GateBlockedError, match="instrumentation"):
        assemble_gate_packet(_draft(), _register(), False, {})
    with pytest.raises(GateBlockedError, match="not green"):
        assemble_gate_packet(
            _draft(), _register(), True, {"claim_substantiation_check": ["finding"]}
        )


def test_gate_packet_presents_the_substantiation_map():
    packet = assemble_gate_packet(
        _draft(),
        _register(),
        True,
        {"claim_substantiation_check": [], "spam_policy_check": []},
        last_approved_text="autoproduct exports rows quickly.",
    )
    assert packet.artifact_text == _draft().text  # the exact artifact
    assert packet.substantiation_map[0].claim_id == "C-101"
    assert packet.substantiation_map[0].evidence_locators == ["bench://july"]
    assert "-autoproduct exports rows quickly." in packet.diff_vs_last_approved


def test_approvals_have_no_unscoped_representation():
    with pytest.raises(ValueError, match="scoped"):
        ApprovalScope(
            artifact_hash="*", channel="content_geo",
            window_start="2026-07-26", window_end="2026-08-02",
        )
    with pytest.raises(ValueError, match="scoped"):
        ApprovalScope(
            artifact_hash=artifact_hash("x"), channel="all",
            window_start="2026-07-26", window_end="2026-08-02",
        )


def test_approval_scope_must_match_the_presented_artifact():
    packet = assemble_gate_packet(
        _draft(), _register(), True, {"claim_substantiation_check": []}
    )
    good = ApprovalScope(
        artifact_hash=packet.artifact_hash, channel="content_geo",
        window_start="2026-07-26", window_end="2026-08-02",
    )
    record = record_approval(packet, good, approver="melody", decision="approve")
    assert record.decision == "approve"

    replayed = ApprovalScope(
        artifact_hash=artifact_hash("some other artifact"), channel="content_geo",
        window_start="2026-07-26", window_end="2026-08-02",
    )
    with pytest.raises(ValueError, match="never generalize"):
        record_approval(packet, replayed, approver="melody", decision="approve")
    with pytest.raises(ValueError, match="named human"):
        record_approval(packet, good, approver="  ", decision="approve")
