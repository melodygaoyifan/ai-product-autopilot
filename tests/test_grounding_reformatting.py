"""Grounding must survive a prompt that reformats what it was given.

A real task died with

    grounding violation: required context missing from the implementer's
    prompt — specs/…/spec.yaml (unread_required)

and the writer had not been blind at all: every acceptance criterion was in
the prompt. The probe was the file's longest line, which happened to be a
`purpose:` inside test_skeletons, and the build prompt renders skeletons as
`- <path>: <purpose> (covers …)`. Same content, different shape. Which line
happened to be longest decided whether the task built — and the violation
is an unrecoverable error, not a retry.
"""
from __future__ import annotations

import yaml

from ai_venture_studio.upstream.context_assembler import (
    ContextManifest,
    ManifestEntry,
    content_hash,
    estimate_tokens,
    make_probe,
    make_probes,
    verify_prompt_grounding,
)

SPEC = {
    "title": "Cart & checkout",
    "design": "A cart module with address validation and order building.",
    "criteria": [
        "When buildOrder is called with a valid address and a non-empty cart, "
        "the system shall return ok true with the order total.",
    ],
    "test_skeletons": [
        {"path": "tests/address.test.js",
         "purpose": "Verify isValidAddress accepts non-empty trimmed strings "
                    "and rejects empties",
         "covers": "AC-2"},
    ],
}


def _entry(raw: str) -> ManifestEntry:
    return ManifestEntry(
        path="specs/cart/spec.yaml", kind="spec", required=True,
        content_hash=content_hash(raw), tokens=estimate_tokens(raw),
        probe=make_probe(raw), probes=make_probes(raw),
    )


def _manifest(raw: str) -> ContextManifest:
    return ContextManifest(task_id="t4", slug="cart", entries=[_entry(raw)],
                           cap_tokens=100_000)


def _build_prompt(spec: dict) -> str:
    """Exactly how build.py renders a spec into the implementer's prompt."""
    return (
        yaml.safe_dump({k: spec[k] for k in ("title", "design", "criteria")},
                       sort_keys=False, allow_unicode=True)
        + "test_skeletons:\n"
        + "\n".join(f"- {s['path']}: {s['purpose']} (covers {s['covers']})"
                    for s in spec["test_skeletons"])
    )


def test_the_reformatted_spec_no_longer_reports_a_violation():
    raw = yaml.safe_dump(SPEC, sort_keys=False, allow_unicode=True)
    assert verify_prompt_grounding(_manifest(raw), _build_prompt(SPEC)) == []


def test_an_artifact_that_truly_never_arrived_is_still_caught():
    """The bug this check exists for — a prompt assembled without the
    contract — must still fire."""
    raw = yaml.safe_dump(SPEC, sort_keys=False, allow_unicode=True)
    violations = verify_prompt_grounding(
        _manifest(raw), "some unrelated prompt about something else entirely"
    )
    assert violations and violations[0].rule == "unread_required"


def test_the_value_half_of_a_key_value_line_is_probed():
    probes = make_probes("purpose: Verify isValidAddress accepts non-empty "
                         "trimmed strings and rejects empties")
    assert any(p.startswith("purpose:") for p in probes)
    assert any(p.startswith("Verify isValidAddress") for p in probes)


def test_several_lines_are_probed_not_just_the_longest():
    text = "\n".join([
        "the single longest line in this artifact by a comfortable margin xx",
        "a second meaningful line that is also long enough to matter",
        "a third meaningful line that is also long enough to matter",
    ])
    probes = make_probes(text)
    assert len(probes) >= 3


def test_a_prompt_containing_only_a_later_line_still_gets_its_receipt():
    """Reformatting can drop the longest line specifically."""
    text = "\n".join([
        "purpose: a very long skeleton purpose line that gets reformatted away",
        "criterion: the system shall return ok true with the order total",
    ])
    manifest = _manifest(text)
    assert verify_prompt_grounding(
        manifest, "criterion: the system shall return ok true with the order total"
    ) == []


def test_old_manifests_without_probes_still_work():
    """Manifests persisted before `probes` existed carry only `probe`."""
    entry = ManifestEntry(path="p", kind="spec", required=True,
                          content_hash="h", tokens=1,
                          probe="the only distinctive line there is here")
    manifest = ContextManifest(task_id="t", slug="s", entries=[entry],
                               cap_tokens=1000)
    assert entry.probes == []
    assert verify_prompt_grounding(
        manifest, "prefix the only distinctive line there is here suffix") == []
    assert verify_prompt_grounding(manifest, "nothing") != []
