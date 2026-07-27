"""Composite confidence score (§09.4.7).

score = voter self-confidence (max 40)
      + verification outcome    (max 40)
      + cross-voter agreement   (max 20)

Weights are engineering defaults pending benchmark calibration (doc 10,
Week 5); the shape (three components, threshold-gated reporting) is the
designed contract.
"""

from __future__ import annotations

from ai_venture_studio.state import Confidence, Severity, VoterFinding

SELF_POINTS = {Confidence.CERTAIN: 40, Confidence.LIKELY: 30, Confidence.POSSIBLE: 15}
VERIFICATION_POINTS = {"VERIFIED": 40, "NEEDS_RUNTIME": 25, None: 0}
AGREEMENT_POINTS = 20

REPORT_THRESHOLD = 80
# Critical/high findings get a lower bar: missing a real critical costs more
# than reviewing a speculative one (asymmetry inverted vs. the default
# precision-first stance, but only at the top severities).
HIGH_SEVERITY_THRESHOLD = 60
_HIGH_SEVERITIES = {Severity.CRITICAL, Severity.HIGH}


def corroborated(finding: VoterFinding, all_findings: list[VoterFinding]) -> bool:
    """Another voter flagged an overlapping line range in the same file."""
    return any(
        other.voter != finding.voter
        and other.file_path == finding.file_path
        and other.line_start <= finding.line_end + 2
        and finding.line_start <= other.line_end + 2
        for other in all_findings
    )


def score_finding(finding: VoterFinding, all_findings: list[VoterFinding]) -> int:
    if finding.verification == "NOT_REPRODUCIBLE":
        return 0
    points = SELF_POINTS[finding.confidence]
    points += VERIFICATION_POINTS.get(finding.verification, 0)
    if corroborated(finding, all_findings):
        points += AGREEMENT_POINTS
    return min(points, 100)


def passes_threshold(finding: VoterFinding, policy=None) -> bool:
    """`policy` is a Policy (ai_venture_studio.policy) when the caller knows the
    workspace; without it the shipped defaults apply."""
    if finding.score is None:
        return False
    if finding.severity in _HIGH_SEVERITIES:
        threshold = (
            policy.high_severity_threshold if policy else HIGH_SEVERITY_THRESHOLD
        )
    else:
        threshold = policy.report_threshold if policy else REPORT_THRESHOLD
    return finding.score >= threshold
