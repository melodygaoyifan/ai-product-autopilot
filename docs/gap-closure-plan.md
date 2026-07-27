# Gap-closure plan (from the 2026-07-26 full audit)

Ordered by leverage ÷ size. Each phase is independently shippable; the
[implementation map](implementation-map.md) rows move as phases land.

## Phase A — small, pure-code (target: v0.28)
1. Web det-tool runners: axe-core / Lighthouse-budget / size-limit as
   availability-gated wrappers (doc 17 §42.1) feeding the web profile.
2. Data NFR vocabulary (doc 18 §48.1): freshness/row-count/eval-floor/
   cost-per-run grammar, perf.py-style lint; data vague-words die.
3. Data lineage declaration + impact check (doc 18 §48.1): declared
   upstream/downstream per dataset; a diff touching a dataset with
   undeclared consumers is a finding.
4. Upstream verdict vocabulary (doc 13): the full ESCALATE_*/BLOCKED_*/
   APPROVE_* constant set, typed, importable by stages.
5. Gate P1 platform-preflight class (doc 17 §41.3): preflight checklist
   schema + check, `platform_submission` already in the autonomy floor.
6. Data-classification tags on .mas artifacts (doc 18 §49.3).
7. CHANGELOG.md (doc 10) — henceforth updated per release.

## Phase B — authoring (target: v0.28–v0.29)
8. Voter charters: DesignFidelity, A11ySemantics, PerformanceDelta (web);
   PlatformFit (小程序); DeviceReality (app) — with 8-fixture gates each,
   wired into `voter-gate` via a profiles/ skills subtree.
9. Data-voter 8-fixture gates (3 voters × 8, doc 19 G13–G14) — same
   format as the 24 product-voter gates.

## Phase C — medium infrastructure (target: v0.29)
10. Observability/cost ledger (doc 09 §6/§10): per-review cost estimate
    from provider usage, tool-audit record, evidence-ledger writer;
    /metrics endpoint on the existing server.
11. Module-spec invariant layer (doc 08/11 §16.3): .mas/specs/*.spec.yaml
    loader (invariants, forbidden_side_effects, expected_change_pattern)
    + SPEC_DRIFT_UNDOCUMENTED check in review.
12. Named signal webhook routes (/webhooks/{sentry,datadog,pagerduty})
    mapping onto the existing /incidents ingestion + dedupe window.

## Phase D — architectural (target: v0.30+, one per release)
13. ✅ v0.32 — Per-voter upstream critique rosters: port discover/plan/spec critics
    onto the product stage_engine (charters + verify + leader), retiring
    the single-panel prompt (doc 13 §25).
14. ✅ v0.31 — GEPA proposer loop, budget-gated by the v0.27 gepa.yaml schema
    (holdout fixtures, one agent per cycle, weekly rollout cap).
15. (in progress, parallel session) Checkpointed graphs for deploy/maintenance (SqliteSaver reuse), then
    upstream — restores mid-stage resume those stages' docs promise.
16. ✅ v0.31 — Secrets layer + encrypted checkpointer serde (doc 09 §3.1).

## Recorded non-goals (stay in the map's Open column)
MCP server partitioning (in-process by ADR'd mapping) · pilot/live-shaped
items (wedge pilot, SSO/IdP, VPC, ERP lane, live experiments/kills) ·
externals on hosts that lack them (k6, netem, device farms, registries).
