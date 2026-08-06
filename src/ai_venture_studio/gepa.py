"""The GEPA proposer (doc 16 §40.1, ADR-U11) — budgeted, holdout-scored,
one agent per cycle.

The disposer (compound --pr) has existed since v0.10; this is the missing
proposer: pick ONE target skill per cycle, generate a charter variation,
score old-vs-new on the voter fixture gate with a HOLDOUT split (the
optimizer never sees the fixtures it is graded on), and emit a proposal
record only when the holdout improves. Everything a human merges; nothing
self-installs. Budget comes from the v0.27 gepa.yaml schema — a proposer
without a budget refuses to run.
"""

from __future__ import annotations

import hashlib
import pathlib

from pydantic import BaseModel

from ai_venture_studio.cascade import GepaBudget
from ai_venture_studio.product.voter_gate import VoterFixture
from ai_venture_studio.providers import get_provider
from ai_venture_studio.yamlx import extract_mapping

GEPA_PROPOSER_MARKER = "GEPA CHARTER PROPOSER"

_PROPOSER_SYSTEM = f"""You are the {GEPA_PROPOSER_MARKER}. Given a voter
charter and the fixture cases it recently missed, propose ONE improved
charter body. Keep the frontmatter contract identical; sharpen the judging
instructions only. Never widen the voter's scope.

Respond with ONLY YAML:
charter: |
  <the full improved charter body>
rationale: one sentence
"""


class GepaError(RuntimeError):
    pass


def holdout_split(
    fixtures: list[VoterFixture], *, fraction: float, salt: str
) -> tuple[list[VoterFixture], list[VoterFixture]]:
    """Deterministic train/holdout split by salted hash — reproducible,
    and the proposer is never shown the holdout (§40.1)."""
    train, holdout = [], []
    for fixture in fixtures:
        digest = hashlib.sha256(f"{salt}:{fixture.label}".encode()).digest()
        (holdout if digest[0] / 255 < fraction else train).append(fixture)
    if not holdout:  # tiny sets: force at least one held-out case
        holdout.append(train.pop())
    return train, holdout


class GepaProposal(BaseModel):
    target: str
    baseline_holdout_rate: float
    candidate_holdout_rate: float
    improved: bool
    rationale: str = ""
    candidate_charter: str = ""
    note: str = ""


def propose_charter(
    *,
    target: str,
    current_charter: str,
    fixtures: list[VoterFixture],
    budget: GepaBudget,
    score_fn,  # (charter_body, fixtures) -> pass rate; injected: the gate
    provider: str = "anthropic",
    model: str = "claude-opus-4-8",
    salt: str = "gepa",
) -> GepaProposal:
    """One cycle, one agent (the budget schema enforces the invariant).
    score_fn is the SAME fixture gate used at registration — the optimizer
    is graded by the judge it must later satisfy."""
    if not budget.budget_rollouts_weekly:
        raise GepaError("gepa.yaml budget_rollouts_weekly is 0 — the proposer "
                        "is disabled; enable it deliberately (ADR-U11)")
    if budget.targets and target not in budget.targets:
        raise GepaError(f"{target!r} is not in gepa.yaml targets — the "
                        "proposer evolves only what a human listed")

    train, holdout = holdout_split(
        fixtures, fraction=budget.holdout_fixture_fraction, salt=salt)
    baseline = score_fn(current_charter, holdout)

    train_labels = [f.label for f in train]  # TRAIN labels only, ever
    raw = get_provider(provider).complete(
        model=model, system=_PROPOSER_SYSTEM,
        user=f"<charter>\n{current_charter}\n</charter>\n"
             f"<train_fixture_labels>\n{train_labels}\n</train_fixture_labels>",
        max_tokens=4096)
    try:
        data = extract_mapping(raw, ("charter",))
    except ValueError as exc:
        raise GepaError(f"proposer emitted no parseable charter: {exc}") from exc
    candidate = str(data.get("charter", ""))
    candidate_rate = score_fn(candidate, holdout)

    improved = candidate_rate > baseline
    return GepaProposal(
        target=target,
        baseline_holdout_rate=round(baseline, 3),
        candidate_holdout_rate=round(candidate_rate, 3),
        improved=improved,
        rationale=str(data.get("rationale", "")),
        candidate_charter=candidate if improved else "",
        note=("holdout improved — emit as a PR for human review; nothing "
              "self-installs" if improved else
              "no holdout improvement — the cycle ends with the record and "
              "nothing else (inconclusive-enters-nothing, again)"))


def write_proposal(workspace: str | pathlib.Path, proposal: GepaProposal,
                   *, at: str) -> pathlib.Path:
    """Persist the proposal — and the cost of producing it.

    `propose_charter` calls a provider; the adapter buffers usage in process
    state and only a caller that knows a workspace can flush it. This is that
    caller. gepa has no production wiring yet, which is precisely why the
    flush goes in now: whoever wires it up inherits the metering rather than
    repeating the compound leak (v0.72.1).
    """
    import yaml

    from ai_venture_studio import spend

    spend.flush(workspace)

    out = pathlib.Path(workspace) / ".mas" / "gepa"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"proposal-{at}-{proposal.target.replace('/', '-')}.yaml"
    path.write_text(yaml.safe_dump(proposal.model_dump(), sort_keys=False))
    return path
