"""The four product-loop stage specs (P0, P1, P2, P4) for the shared
engine — writer contracts, deterministic tool closures, gates, and
artifact persistence.

Writers generate; the deterministic layer built in v0.13-v0.18 judges;
humans decide at PL1/PL2/PL5. Every writer contract embeds the discipline
the substrate enforces (typed claims, falsifiers, no synthetic users), so
the revision loop teaches the writer the rules the gate will apply.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import yaml
from pydantic import BaseModel, Field

from ai_venture_studio.evidence import load_metric_vocabulary
from ai_venture_studio.evidence.cohort import CohortReading
from ai_venture_studio.evidence.gate_pl4 import OutcomeReason, gate_pl4
from ai_venture_studio.product.claim_lint import lint_ledger
from ai_venture_studio.product.claims import load_product_policy
from ai_venture_studio.product.injection import injection_scan
from ai_venture_studio.product.kill_registry import load_kill_registry
from ai_venture_studio.product.market import gate_pl1_entry
from ai_venture_studio.product.opportunity import (
    DemandHypothesis,
    OpportunityCandidate,
    gate_pl0,
)
from ai_venture_studio.product.persona_scan import synthetic_persona_scan
from ai_venture_studio.product.prd import PRD, prd_lint
from ai_venture_studio.product.sizing import SizingFactor, TopDownCrosscheck, sizing_calc
from ai_venture_studio.product.sources import load_signal_sources, source_standing_check
from ai_venture_studio.product.stage_engine import StageSpec

OPPORTUNITY_WRITER_MARKER = "OPPORTUNITYWRITER (P0)"
MARKET_WRITER_MARKER = "MARKETWRITER (P1)"
PRD_WRITER_MARKER = "PRDWRITER (P2)"
EVIDENCE_WRITER_MARKER = "EVIDENCEWRITER (P4)"

_CLAIM_RULES = """
Claim discipline (claim_lint will check every rule mechanically):
- every claim: id, text, kind, source_type
  (primary_measured|primary_cited|third_party_report|user_reported|model_inference),
  falsifier; evidence entries with method+locator+retrieved_at for anything
  that is not model_inference; n for any proportion; expires for market facts.
- quantitative claims are never model_inference; causal verbs require
  primary_measured; never author a user quote or persona (ADR-U23).
"""


def _mas(workspace: str) -> pathlib.Path:
    return pathlib.Path(workspace) / ".mas"


def _write(path: pathlib.Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _write_yaml(path: pathlib.Path, doc: dict) -> str:
    return _write(path, yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))


def _lint_dicts(issues) -> list[dict]:
    return [i.model_dump() for i in issues]


# --- P0 Opportunity (§20.54) ---------------------------------------------------


class OpportunitySet(BaseModel):
    candidates: list[OpportunityCandidate]
    narrative: str = ""


_OPPORTUNITY_SYSTEM = f"""You are the {OPPORTUNITY_WRITER_MARKER}. Turn the
clustered signals into >=3 candidate opportunities. Cluster and count real
artifacts; never synthesize demand no signal shows. Every candidate needs a
falsifiable demand hypothesis and a NAMED cheapest test ("build an MVP" is
not a test).

Evidence locators must be the signals' own `locator` values, VERBATIM —
one evidence entry per underlying signal. A locator you invent (or a
signal id used as a locator) has no declared standing and fails the build.
{_CLAIM_RULES}
Respond with ONLY YAML:
candidates:
  - id: cand-...
    statement: ...
    hypothesis: ...
    falsifier: ...
    cheapest_test: ...
    claims:
      - {{id: ..., text: ..., kind: user_need, source_type: user_reported,
          n: ..., evidence: [{{method: ..., locator: ..., retrieved_at: ...}}],
          falsifier: ...}}
"""


def opportunity_spec(
    workspace: str, *, today: dt.date | None = None
) -> StageSpec:
    mas = _mas(workspace)
    policy = load_product_policy(mas)

    def parse(data: dict) -> tuple[OpportunitySet, str]:
        candidates = []
        for entry in data.get("candidates") or []:
            if not isinstance(entry, dict):
                raise ValueError(f"candidate is not a mapping: {entry!r}")
            candidates.append(
                OpportunityCandidate(
                    id=str(entry.get("id", "?")),
                    statement=str(entry.get("statement", "")),
                    demand_hypothesis=DemandHypothesis(
                        statement=str(entry.get("hypothesis", "")),
                        falsifier=str(entry.get("falsifier", "")),
                    ),
                    cheapest_test=str(entry.get("cheapest_test", "")),
                    claim_ledger={"claims": entry.get("claims") or []},
                )
            )
        artifact = OpportunitySet(candidates=candidates)
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        return artifact, text

    def det_tools(artifact: OpportunitySet) -> list[dict]:
        sources = load_signal_sources(mas)
        findings: list[dict] = []
        for candidate in artifact.candidates:
            findings += _lint_dicts(
                lint_ledger(candidate.claim_ledger, "opportunity",
                            today=today, policy=policy)
            )
            findings += _lint_dicts(
                source_standing_check(candidate.claim_ledger, sources)
            )
            findings += [
                f.model_dump()
                for f in synthetic_persona_scan(candidate.statement, mas)
            ]
        return findings

    def gate(artifact: OpportunitySet) -> dict:
        result = gate_pl0(
            artifact.candidates, load_kill_registry(mas), today=today, policy=policy
        )
        return {"passed": result.passed,
                "findings": [f.model_dump() for f in result.findings],
                "ranked": result.ranked_candidate_ids,
                "killed_matches": {
                    c.id: [m.model_dump() for m in c.killed_matches]
                    for c in artifact.candidates if c.killed_matches
                }}

    def persist(artifact: OpportunitySet, workspace: str) -> list[str]:
        root = pathlib.Path(workspace)
        body = "\n\n".join(
            f"## {c.id}\n\n{c.statement}\n\n- hypothesis: {c.demand_hypothesis.statement}"
            f"\n- falsifier: {c.demand_hypothesis.falsifier}"
            f"\n- cheapest test: {c.cheapest_test}"
            for c in artifact.candidates
        )
        merged = {"claims": [c for cand in artifact.candidates
                             for c in cand.claim_ledger.get("claims", [])]}
        return [
            _write(root / "product" / "opportunities.md",
                   f"# Opportunity candidates (Gate PL0)\n\n{body}\n"),
            _write_yaml(root / "claims" / "opportunity.claim.yaml", merged),
        ]

    def voter_context(artifact: OpportunitySet, artifact_text: str) -> str:
        # The Fit voter judges distance against .mas/strategy.yaml — the
        # declared constraints must be in front of it, not a ghost reference.
        from ai_venture_studio.product.strategy import load_strategy

        strategy = load_strategy(mas)
        if not (strategy.constraints or strategy.product or strategy.segments):
            return artifact_text
        return artifact_text + "\n" + yaml.safe_dump(
            {"strategy": strategy.model_dump()}, sort_keys=False, allow_unicode=True
        )

    return StageSpec(
        name="opportunity",
        writer_system=_OPPORTUNITY_SYSTEM,
        expected_keys=("candidates",),
        skills_subdir="opportunity",
        parse=parse,
        det_tools=det_tools,
        gate=gate,
        persist=persist,
        voter_context=voter_context,
    )


# --- P1 Market & Viability (§20.55) ---------------------------------------------


class MarketAssessment(BaseModel):
    narrative: str
    ledger: dict
    factors: list[SizingFactor]
    top_down: TopDownCrosscheck | None = None
    sizing: dict = Field(default_factory=dict)


_MARKET_SYSTEM = f"""You are the {MARKET_WRITER_MARKER}. Assess market and
viability for the candidate. Sizing is bottom-up from named, individually
sourced factors — a top-down figure may appear only as a labeled
third_party_report cross-check. Competitor facts cite probe snapshots or
are model_inference by definition.
{_CLAIM_RULES}
Respond with ONLY YAML:
narrative: ...
claims: [...]
sizing:
  factors:
    - {{name: ..., value: ..., source_type: ...,
        sensitivity: [low, high] (required unless primary_measured), n: ...}}
  top_down_crosscheck: {{value: ..., note: ...}}  # optional
"""


def market_spec(
    workspace: str,
    *,
    today: dt.date | None = None,
    disconfirmation_answered: bool = False,
    regulatory_triaged: bool = False,
) -> StageSpec:
    mas = _mas(workspace)
    policy = load_product_policy(mas)

    def parse(data: dict) -> tuple[MarketAssessment, str]:
        sizing = data.get("sizing") or {}
        factors = [SizingFactor(**f) for f in sizing.get("factors") or []]
        crosscheck = sizing.get("top_down_crosscheck")
        # The cross-check is optional; an honest "unavailable"/null value is
        # absence, not a schema violation (first real-provider smoke: the
        # writer correctly reported no analyst figure exists for the niche).
        if not isinstance(crosscheck, dict) or not isinstance(
            crosscheck.get("value"), (int, float)
        ):
            crosscheck = None
        artifact = MarketAssessment(
            narrative=str(data.get("narrative", "")),
            ledger={"claims": data.get("claims") or []},
            factors=factors,
            top_down=TopDownCrosscheck(**crosscheck) if crosscheck else None,
        )
        return artifact, yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

    def det_tools(artifact: MarketAssessment) -> list[dict]:
        findings = _lint_dicts(
            lint_ledger(artifact.ledger, "market", today=today, policy=policy)
        )
        sizing = sizing_calc(artifact.factors, top_down_crosscheck=artifact.top_down)
        artifact.sizing = sizing.model_dump()
        findings += [i.model_dump() for i in sizing.issues]
        findings += _lint_dicts(
            source_standing_check(artifact.ledger, load_signal_sources(mas))
        )
        findings += [
            f.model_dump()
            for f in injection_scan(artifact.ledger, mas)
            if f.rule in ("contaminated", "snapshot_drift")
        ]
        return findings

    def gate(artifact: MarketAssessment) -> dict:
        from ai_venture_studio.product.sizing import SizingResult

        entry = gate_pl1_entry(
            artifact.ledger,
            SizingResult(**artifact.sizing),
            mas_dir=mas,
            disconfirmation_answered=disconfirmation_answered,
            regulatory_triaged=regulatory_triaged,
            today=today,
            policy=policy,
        )
        return {"passed": entry.passed, "findings": entry.findings,
                "human_gate": "PL1 — record the decision with "
                              "`avs market-approve`"}

    def persist(artifact: MarketAssessment, workspace: str) -> list[str]:
        root = pathlib.Path(workspace)
        return [
            _write(root / "market" / "market.md",
                   f"# Market assessment (Gate PL1)\n\n{artifact.narrative}\n"),
            _write_yaml(root / "market" / "sizing.yaml", artifact.sizing),
            _write_yaml(root / "claims" / "market.claim.yaml", artifact.ledger),
        ]

    return StageSpec(
        name="market",
        writer_system=_MARKET_SYSTEM,
        expected_keys=("claims", "narrative"),
        skills_subdir="market",
        parse=parse,
        det_tools=det_tools,
        gate=gate,
        persist=persist,
    )


# --- P2 PRD (§20.56) --------------------------------------------------------------


class PrdBundle(BaseModel):
    prd: PRD
    prose: str
    ledger: dict = Field(default_factory=lambda: {"claims": []})
    planning_tasks: list[dict] = Field(default_factory=list)


_PRD_SYSTEM = f"""You are the {PRD_WRITER_MARKER}. Write the PRD: who, what
problem, why now — never which modules or EARS criteria (prd_lint fails
both). >=2 non-goals, >=1 kill criterion, every outcome a vocabulary metric
with instrumentation that exists or becomes a task. evidence_refs must be
claim IDs from the market/opportunity ledgers.
{_CLAIM_RULES}
Respond with ONLY YAML:
prd:
  id: PRD-...
  problem_statement: ...
  evidence_refs: [...]
  affected_segment: {{name: ..., size_claim: ...}}
  non_goals: [..., ...]
  outcomes:
    - {{id: O-1, metric: ..., definition_ref: ..., baseline: {{...}},
        target: {{value: ..., by: ...}},
        instrumentation: {{event: ..., exists: true|false}}}}
  demand_hypotheses:
    - {{id: H-1, statement: ..., falsifier: ...,
        check: {{stage: P4, method: cohort, window_days: ...}}}}
  scope_tier: thin|standard|deep
  kill_criteria: [...]
prose: |
  the prd.md document text
claims: []
"""


def prd_spec(
    workspace: str,
    *,
    metrics_dir: str | pathlib.Path | None = None,
    ledger_claim_ids: set[str] | None = None,
    today: dt.date | None = None,
) -> StageSpec:
    mas = _mas(workspace)
    policy = load_product_policy(mas)
    root = pathlib.Path(workspace)
    metrics_path = pathlib.Path(metrics_dir) if metrics_dir else root / "metrics"
    # The writer can only cite metrics that exist (§22.62.3, human-owned) —
    # so it must be told what exists (first real-provider smoke: it invented
    # plausible metrics for two straight revisions because nothing said
    # what the vocabulary contained).
    vocabulary_now = load_metric_vocabulary(metrics_path)
    vocabulary_note = (
        "\nMetric vocabulary (outcomes may cite ONLY these ids; if none fits, "
        "cite the closest and name the missing metric in open_questions — a "
        "human must author its definition file first):\n"
        + "\n".join(
            f"- {m.id}: {m.definition}" for m in vocabulary_now.values()
        )
        + "\n"
    )

    def _known_claim_ids() -> set[str]:
        if ledger_claim_ids is not None:
            return ledger_claim_ids
        ids = set()
        for name in ("market", "opportunity"):
            path = root / "claims" / f"{name}.claim.yaml"
            if path.exists():
                doc = yaml.safe_load(path.read_text()) or {}
                ids |= {
                    str(c.get("id"))
                    for c in doc.get("claims") or []
                    if isinstance(c, dict)
                }
        return ids

    def parse(data: dict) -> tuple[PrdBundle, str]:
        spec = data.get("prd")
        if not isinstance(spec, dict):
            raise ValueError("response lacks a 'prd' mapping")
        try:
            prd = PRD(**spec)
        except Exception as exc:  # noqa: BLE001 — schema failure feeds revision
            raise ValueError(str(exc)) from exc
        bundle = PrdBundle(
            prd=prd,
            prose=str(data.get("prose", "")),
            ledger={"claims": data.get("claims") or []},
        )
        return bundle, yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

    def det_tools(bundle: PrdBundle) -> list[dict]:
        issues, tasks = prd_lint(
            bundle.prd,
            bundle.prose,
            vocabulary=load_metric_vocabulary(metrics_path),
            ledger_claim_ids=_known_claim_ids(),
        )
        bundle.planning_tasks = [t.model_dump() for t in tasks]
        findings = [i.model_dump() for i in issues]
        if bundle.ledger.get("claims"):
            findings += _lint_dicts(
                lint_ledger(bundle.ledger, "prd", today=today, policy=policy)
            )
        return findings

    def gate(bundle: PrdBundle) -> dict:
        return {"passed": True,  # det_tools were the deterministic gate
                "planning_tasks": bundle.planning_tasks,
                "human_gate": "PL2 — acknowledge kill criteria + tier with "
                              "`avs prd-approve`"}

    def persist(bundle: PrdBundle, workspace: str) -> list[str]:
        paths = [
            _write_yaml(root / "product" / "prd.yaml",
                        {"prd": bundle.prd.model_dump()}),
            _write(root / "product" / "prd.md", bundle.prose),
        ]
        if bundle.ledger.get("claims"):
            paths.append(_write_yaml(root / "claims" / "prd.claim.yaml", bundle.ledger))
        if bundle.planning_tasks:
            paths.append(_write_yaml(root / "product" / "planning-tasks.yaml",
                                     {"tasks": bundle.planning_tasks}))
        return paths

    def voter_context(bundle: PrdBundle, artifact_text: str) -> str:
        # Voters must see the tasks prd_lint generated: an uninstrumented
        # outcome WITH a generated task is instrumented-or-tasked (§20.56.2),
        # not a gap — flagging it anyway is noise (first real-provider smoke).
        if not bundle.planning_tasks:
            return artifact_text
        return artifact_text + "\n" + yaml.safe_dump(
            {"generated_planning_tasks": bundle.planning_tasks,
             "note": "these instrumentation tasks were mechanically generated "
                     "by prd_lint and already exist — outcomes they cover are "
                     "instrumented-or-tasked, not unmeasurable"},
            sort_keys=False, allow_unicode=True,
        )

    return StageSpec(
        name="prd",
        writer_system=_PRD_SYSTEM + vocabulary_note,
        expected_keys=("prd",),
        skills_subdir="prd",
        parse=parse,
        det_tools=det_tools,
        gate=gate,
        persist=persist,
        voter_context=voter_context,
    )


# --- P4 Evidence (§22.62) ------------------------------------------------------------


class EvidenceBundle(BaseModel):
    narrative: str
    verdicts: list[dict]
    ledger: dict
    reasons: list[dict] = Field(default_factory=list)


_EVIDENCE_SYSTEM = f"""You are the {EVIDENCE_WRITER_MARKER}. Read the cohort
readings you are given — never invent one — and write the evidence bundle:
per-outcome readings against targets, and a verdict for each hypothesis
against its PRE-STATED falsifier (supported | not_supported |
insufficient_evidence; insufficient states the n it would take). An outcome
you cannot read gets a typed reason, never silence.
{_CLAIM_RULES}
Respond with ONLY YAML:
narrative: ...
verdicts:
  - {{id: H-..., verdict: ..., falsifier_met: true|false}}
reasons:  # only for outcomes without readings
  - {{outcome_id: ..., reason: insufficient_evidence|window_incomplete|instrumentation_pending,
      detail: ...}}
claims: [...]
"""


def evidence_spec(
    workspace: str,
    *,
    prd_outcome_ids: list[str],
    readings: dict[str, CohortReading],
    today: dt.date | None = None,
) -> StageSpec:
    mas = _mas(workspace)
    policy = load_product_policy(mas)

    def parse(data: dict) -> tuple[EvidenceBundle, str]:
        bundle = EvidenceBundle(
            narrative=str(data.get("narrative", "")),
            verdicts=[v for v in data.get("verdicts") or [] if isinstance(v, dict)],
            ledger={"claims": data.get("claims") or []},
            reasons=[r for r in data.get("reasons") or [] if isinstance(r, dict)],
        )
        if not bundle.verdicts:
            raise ValueError("an evidence bundle with no hypothesis verdicts "
                             "resolved nothing")
        return bundle, yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

    def det_tools(bundle: EvidenceBundle) -> list[dict]:
        return _lint_dicts(
            lint_ledger(bundle.ledger, "evidence", today=today, policy=policy)
        )

    def gate(bundle: EvidenceBundle) -> dict:
        try:
            reasons = [OutcomeReason(**r) for r in bundle.reasons]
        except ValueError as exc:
            return {"passed": False, "detail": f"malformed reason: {exc}"}
        result = gate_pl4(
            prd_outcome_ids, readings, reasons,
            ledger_issue_count=len(det_tools(bundle)),
        )
        return result.model_dump()

    def persist(bundle: EvidenceBundle, workspace: str) -> list[str]:
        root = pathlib.Path(workspace)
        return [
            _write(root / "evidence" / "evidence.md",
                   f"# Evidence bundle (Gate PL4)\n\n{bundle.narrative}\n"),
            _write_yaml(root / "evidence" / "verdicts.yaml",
                        {"verdicts": bundle.verdicts,
                         "readings": {k: v.model_dump() for k, v in readings.items()}}),
            _write_yaml(root / "claims" / "evidence.claim.yaml", bundle.ledger),
        ]

    return StageSpec(
        name="evidence",
        writer_system=_EVIDENCE_SYSTEM,
        expected_keys=("verdicts", "narrative"),
        skills_subdir="evidence",
        parse=parse,
        det_tools=det_tools,
        gate=gate,
        persist=persist,
    )
