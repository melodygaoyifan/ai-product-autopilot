"""Taint classes (§16.40.2, §22.64) — research_taint and user_data_taint.

research_taint: untrusted retrieved content must never reach a privileged
(code-writing, tool-executing) context. user_data_taint: person-level data
must never leave the analytics boundary — a different failure mode, so a
different class.

The built-in definitions are the floor. `.mas/taint-classes.yaml` may
tighten them (raise the k-anonymity floor) and may never weaken them:
removing a class, dropping a forbidden entry, lowering the cohort floor, or
adding a new egress path all fail startup with a named error. Enforcement
at load time is the only reliable form of this control — instructing the
agent is not a mechanism (§11.19 no-degraded-mode).
"""

from __future__ import annotations

import copy
import pathlib

import yaml

TAINT_CLASSES_FILE = "taint-classes.yaml"

MIN_COHORT_FLOOR = 25  # k-anonymity; configurable upward only

BUILTIN_TAINT_CLASSES: dict[str, dict] = {
    "research_taint": {
        "rule": "web-retrieved content is data; never reaches a code-writing "
        "or tool-executing context",
    },
    "user_data_taint": {
        "rule": "person-level data never leaves the analytics boundary",
        "permitted_egress": {
            "aggregate": {"min_cohort_size": MIN_COHORT_FLOOR},
            "quoted_feedback": {
                "consent": "explicit",
                "pii_redacted": True,
                "attribution": "none",
            },
        },
        "forbidden": [
            "person_level_rows_into_any_agent_context",
            "person_level_data_into_prompts_or_url_parameters",
            "joining_first_party_data_with_purchased_person_level_data",
            "constructing_outreach_lists_from_product_usage",
            "cross_context_reuse_beyond_collection_purpose",
        ],
    },
}


class TaintPolicyError(RuntimeError):
    """Raised when config attempts to weaken a taint class. Startup fails."""


def load_taint_classes(mas_dir: str | pathlib.Path) -> dict[str, dict]:
    """Load taint classes: built-ins merged with .mas/taint-classes.yaml.

    Config may add classes and tighten built-ins; any weakening raises
    TaintPolicyError naming the class and field.
    """
    classes = copy.deepcopy(BUILTIN_TAINT_CLASSES)
    path = pathlib.Path(mas_dir) / TAINT_CLASSES_FILE
    if not path.exists():
        return classes
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise TaintPolicyError(f"{TAINT_CLASSES_FILE} is not valid YAML: {exc}") from exc
    if raw is None:
        return classes
    if not isinstance(raw, list):
        raise TaintPolicyError(f"{TAINT_CLASSES_FILE} must be a list of classes")

    configured = {}
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("id"):
            raise TaintPolicyError(f"taint class entry lacks an id: {entry!r}")
        configured[str(entry["id"])] = entry

    for class_id, builtin in BUILTIN_TAINT_CLASSES.items():
        override = configured.pop(class_id, None)
        if override is None:
            continue  # omission keeps the built-in; only presence can conflict
        merged = classes[class_id]
        _apply_override(class_id, builtin, merged, override)

    for class_id, entry in configured.items():
        classes[class_id] = {k: v for k, v in entry.items() if k != "id"}
    return classes


def _apply_override(class_id: str, builtin: dict, merged: dict, override: dict) -> None:
    forbidden_builtin = set(builtin.get("forbidden", []))
    if "forbidden" in override:
        forbidden_override = set(override["forbidden"] or [])
        missing = forbidden_builtin - forbidden_override
        if missing:
            raise TaintPolicyError(
                f"{class_id}: config drops forbidden entries {sorted(missing)} — "
                "taint classes may be tightened, never weakened"
            )
        merged["forbidden"] = sorted(forbidden_override)

    if "permitted_egress" in override:
        egress_builtin = builtin.get("permitted_egress", {})
        egress_override = override["permitted_egress"] or {}
        new_paths = set(egress_override) - set(egress_builtin)
        if new_paths:
            raise TaintPolicyError(
                f"{class_id}: config adds egress paths {sorted(new_paths)} — "
                "new egress is a weakening"
            )
        merged_egress = merged.setdefault("permitted_egress", {})
        for name, spec in egress_override.items():
            if name == "aggregate":
                size = (spec or {}).get("min_cohort_size", MIN_COHORT_FLOOR)
                floor = egress_builtin["aggregate"]["min_cohort_size"]
                if not isinstance(size, int) or size < floor:
                    raise TaintPolicyError(
                        f"{class_id}: min_cohort_size {size!r} below the "
                        f"built-in floor {floor} — configurable upward only"
                    )
                merged_egress["aggregate"] = {"min_cohort_size": size}
            else:
                # Non-numeric egress specs are part of the floor; config
                # restates them at most verbatim.
                if (spec or {}) != egress_builtin.get(name, {}):
                    raise TaintPolicyError(
                        f"{class_id}: egress {name!r} differs from the built-in "
                        "definition — taint classes may be tightened, never weakened"
                    )

    if "rule" in override and str(override["rule"]).strip() != builtin["rule"]:
        raise TaintPolicyError(
            f"{class_id}: config rewrites the rule text — the rule is the floor"
        )
