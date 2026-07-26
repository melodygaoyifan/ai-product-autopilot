"""Evidence bundle exporter v0 — unsigned (§19 G2 Day 9-10).

Gate decisions, verdicts, overrides, and blocked voters already exist as
structured state in the YAML mirror (§09.6); this module assembles them
per-review into one bundle a CAB can read. Signing arrives with the
attestation ledger (G15) — v0 is the format, not the guarantee, and the
header says so.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_EVIDENCE_DIR = ".mas/evidence"

# Mirror nodes that carry gate/verdict/override state worth attesting.
_ATTESTABLE_KEYS = (
    "verdict", "decision", "gate", "dor_pass", "override", "resumed_by",
)


def _load_steps(review_dir: Path) -> list[dict]:
    steps = []
    for path in sorted(review_dir.glob("[0-9][0-9]-*.yaml")):
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(record, dict):
            steps.append(record)
    return steps


def build_evidence_bundle(repo_dir: str | Path, review_id: str) -> str:
    """Markdown bundle for one review's audit trail. Raises FileNotFoundError
    when the review has no mirror — a bundle is never fabricated."""
    review_dir = Path(repo_dir) / ".mas" / "reviews" / review_id
    if not review_dir.is_dir():
        raise FileNotFoundError(
            f"no YAML mirror at {review_dir} — nothing to attest"
        )
    steps = _load_steps(review_dir)
    if not steps:
        raise FileNotFoundError(f"{review_dir} contains no mirror steps")

    lines = [
        f"# Evidence bundle — review {review_id}",
        "",
        "> v0 (unsigned) — assembled from the YAML mirror audit trail. "
        "Ledger-backed signing lands with the attestation ledger.",
        "",
        f"Steps recorded: {len(steps)}",
        "",
        "## Gate decisions and verdicts",
        "",
    ]
    attested = 0
    for step in steps:
        marks = {k: step[k] for k in _ATTESTABLE_KEYS if k in step and step[k] is not None}
        if not marks:
            continue
        attested += 1
        rendered = ", ".join(f"{k}={_short(v)}" for k, v in sorted(marks.items()))
        lines.append(
            f"- step {step.get('step', '?')} `{step.get('node', '?')}` "
            f"({step.get('written_at', 'unknown time')}): {rendered}"
        )
    if attested == 0:
        lines.append(
            "- none recorded — this trail contains no gate/verdict state; "
            "it is NOT submission evidence"
        )

    lines += ["", "## Full step index", ""]
    for step in steps:
        lines.append(f"- {step.get('step', '?'):>2}. {step.get('node', '?')}")
    lines.append("")
    return "\n".join(lines)


def _short(value: object, limit: int = 120) -> str:
    text = str(value).replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def write_evidence_bundle(repo_dir: str | Path, review_id: str) -> Path:
    bundle = build_evidence_bundle(repo_dir, review_id)
    out_dir = Path(repo_dir) / _EVIDENCE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{review_id}.md"
    path.write_text(bundle, encoding="utf-8")
    return path
