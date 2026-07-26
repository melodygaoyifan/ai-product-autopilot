"""Data-classification tags on .mas artifacts (doc 18 §49.3).

Every .mas artifact class carries a classification; the check flags
artifacts whose class demands a tag and has none, and refuses downgrades
(confidential → internal is a decision, not an edit)."""

from __future__ import annotations

CLASSIFICATIONS = ("public", "internal", "confidential")
DEFAULT_CLASS_BY_ARTIFACT = {
    "reviews": "internal", "evidence": "confidential",
    "claims": "internal", "kill-registry": "internal",
    "attestation": "internal", "telemetry": "public",
}


def classification_check(artifacts: dict[str, str | None]) -> list[str]:
    """artifacts: {artifact_class: declared_classification|None}."""
    findings = []
    order = {c: i for i, c in enumerate(CLASSIFICATIONS)}
    for artifact, declared in sorted(artifacts.items()):
        floor = DEFAULT_CLASS_BY_ARTIFACT.get(artifact, "internal")
        if declared is None:
            findings.append(f"{artifact}: no classification tag (floor: {floor})")
        elif declared not in CLASSIFICATIONS:
            findings.append(f"{artifact}: unknown classification {declared!r}")
        elif order[declared] < order[floor]:
            findings.append(f"{artifact}: {declared} downgrades the {floor} "
                            "floor — a decision, not an edit")
    return findings
