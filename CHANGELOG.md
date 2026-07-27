# Changelog

SemVer over the enumerated contract surface (CONTRIBUTING.md). One entry
per release, newest first; the git tags v0.8.0–v0.27.0 predate this file
and are summarized in the README roadmap and docs/implementation-map.md.

## v0.36.0 — the live-loop instrument for the v3.0.0 design gate
- autoproduct loop: reads a cycle's artifacts (stages P0-P5, gates
  PL1/PL2/PL3/PL5) and reports the three v3.0.0 criteria with reasons.
  States, never decides: a cycle where nothing fired is NOT the gate, and
  a recorded 'continue' is not either — the gate is about the loop's
  ability to stop, so only a human kill-or-pivot at PL5 closes it
  (invariant 14.20, ADR-U19). Exit 3 when a fired criterion is waiting on
  a human.
- launch/cycle.yaml: loop-entry declaration. This repo's own cycle entered
  at P2 (the product predated the loop), recorded with its reason instead
  of left as a silent gap; P0/P1 are in scope for cycle 2.
- docs/v3-live-loop.md: what closes the gate, why the system cannot close
  it for itself, and the exact field a human records.
- Current honest state: V3-1 and V3-2 met, V3-3 not — the launch PRD's
  only kill criterion needs four consecutive logged attention weeks and
  the log holds one untracked week.
- Suite: 766 -> 778 hermetic tests

## v0.35.0 — the last small open items: review-voter gates, policy thresholds, the ready-queue fix
- Review voters now register like every other roster (§11.19):
  `autoproduct review-gate` runs each of the six core charters against 8
  fixtures (4 positive / 2 negative / 2 boundary, unified diffs) through
  the REAL Voter seat, ≥87.5% to register, recorded under `review/<voter>`
  in `.mas/voter-registry.yaml`. The vote node fails closed on a FAILED
  voter, reports unregistered ones, and refuses to review at all if the
  whole roster failed. Review voters no longer ride `bench` alone.
- Policy thresholds move into `.mas/project.yaml` (`policy:` block, doc 09
  open item): max_reviewable_lines, report_threshold,
  high_severity_threshold, rootcause_confidence_min. Unknown keys are a
  loud error (a typo silently keeping the default is worse), ranges are
  bounded so a project cannot set a meaningless bar, effective values are
  recorded in the run mirror, and any threshold looser than the shipped
  default is stamped into the leader summary — a lowered bar never hides
  inside a clean-looking verdict.
- Fixed: `next_tasks` matched a `task_id` field Spec never had, so the
  ready queue never advanced past the first task. It now reads the
  `(task:<id>)` marker in the spec request — one shared definition of
  "built", reused by the Studio's per-task progress.
- Suite: 737 → 766 hermetic tests

## v0.34.0 — Studio live progress, interrupted-build recovery UX, the wire-up gate
- Building page shows per-task state (from the same workspace files the
  CLI writes) updating in place via /status polling — signals s1/s3, "it
  looks frozen while it works"; one reload when the worker exits
- Interrupted builds (dead worker, no report) get their own page: kept
  modules shown ✅, per-module 继续 retry buttons through the existing
  retry-task path (a blanket rebuild would trip the SCR freeze on built
  specs — deliberately not offered), reset clears the stale pid marker
- Wire-up gate (tests/test_studio_wireup.py): every form action, fetch,
  link, and image src rendered by any Studio state must resolve to a
  registered route with the right method — and every route must be
  rendered by some state; the /status JSON contract is pinned to what the
  building-page script reads
- README: bring-your-own-keys contract spelled out (no shipped keys, no
  proxy, no metered backend), AUTOPRODUCT_CHECKPOINT_KEY documented,
  roadmap rows v0.31-v0.34, stale per-review-only recovery limit fixed

## v0.33.0 — gap plan D15 + D16 remainder: checkpointed deploy/maintenance, encrypted checkpoints
- Deploy review and maintenance rebuilt as LangGraph graphs on the shared
  `.mas/checkpoints.db` saver (thread ids `deploy:<id>` / `incident:<id>`):
  a crash mid-vote or mid-root-cause resumes from the last completed
  super-step via `autoproduct recover` (now covering all three graphs)
  instead of re-paying the pipeline; mirror step names, verdict taxonomies,
  lint-only degraded mode, and the recommend-only ceiling unchanged
- Encrypted checkpointer serde (doc 09 §3.1): `AUTOPRODUCT_CHECKPOINT_KEY`
  (raw or `secret://ENV`) encrypts checkpoint rows at rest via LangGraph's
  EncryptedSerializer (AES, pycryptodome availability-gated); a key that
  cannot be honored errors loudly — never a silent plaintext fallback;
  encryption state stamped into every run's meta.yaml; the YAML mirror
  stays deliberately plaintext (§09.6 audit asymmetry)
- Suite: 688 → 694 on the D15 branch (727 after merging v0.32; ledger
  PC-1 synced at the merge)

## v0.33.1 — operator pass: live records + installable package
- Live operator records: first Gate PL5 evaluation (nothing fired — 0 of
  4 attention weeks exist; decision explicitly NOT due), the launch
  experiment's power verdict against real traffic (n=1 unique visitor vs
  2,936 required → BLOCKED(INSUFFICIENT_POWER), exactly as pre-registered;
  clone spike recorded as CI-confounded), and the append-only
  weekly-attention log (2026-W30 honestly `not_tracked`; discipline
  starts 2026-W31) — each with a test that re-derives it
- Packaging: voter charters moved into the package
  (`src/autoproduct/skills/`, root symlink kept) so the installed wheel
  runs stage commands; pip-installed builds previously crashed loading
  charters. MIT LICENSE file added; PyPI metadata completed
- Suite: 727 → 732 hermetic tests on the rebased tree (ledger PC-1 synced)

## v0.32.0 — gap plan D13: upstream critique rosters
- Discover/plan/spec critics ported onto the shared stage engine as 14
  registered charter voters (discovery: desirability/feasibility/
  viability/scope-discipline; planning: completeness/dependency-realism/
  risk-sequencing/parallelization-safety/estimate-sanity; spec:
  testability/consistency/completeness/ambiguity/interface-impact — doc
  13 §25.1), each behind the 8-fixture registration gate; the three
  single-panel critic prompts retired
- `run_critique_roster` extracted from the P-stage engine: charter voters
  with no cross-visibility → per-finding fresh verify → leader; failed
  gate runs exclude the voter, unregistered voters are reported
- Suite: 688 → 721 hermetic tests (ledger PC-1 synced)

## v0.31.0 — gap plan D14 + D16: GEPA proposer, secrets layer
- GEPA proposer (`gepa.py`): budget-gated by the v0.27 `gepa.yaml` schema
  (refuses at zero weekly rollouts or unlisted targets), deterministic
  salted-hash holdout split the proposer never sees, old-vs-new charter
  scored by the same fixture gate voters register through; improvements
  emit a `.mas/gepa/` proposal record for human review — nothing
  self-installs
- Secrets layer (`secrets.py`): `secret://ENV` resolution that errors
  loudly on missing values, `Secret` with masked repr and a single
  deliberate `reveal()`, `scrub()` stripping every resolved value from
  outbound text
- Suite: 673 → 688 hermetic tests (ledger PC-1 synced)

## v0.30.0 — audit gap closures, phase C
- Cost/observability ledger: config-priced estimates, unpriced-call
  visibility, monthly cap check, tool-audit + evidence-ledger writers,
  Prometheus /metrics
- Module-spec invariant layer with SPEC_DRIFT_UNDOCUMENTED
- Named signal webhooks (sentry/datadog/pagerduty) with dedupe window

## v0.29.0 — audit gap closures, phase B
- Voter families: voter-gate now serves web/miniprogram/app/data alongside
  the product stages (same skills+fixtures contract)
- Five profile voter charters authored; 8-fixture gates for them and for
  the three data voters (64 new fixture cases)

## v0.28.0 — audit gap closures, phase A
- Web det-tool runners (axe/Lighthouse/size-limit, availability-gated)
- Data NFR grammar + lineage impact check (doc 18 §48.1)
- Upstream verdict vocabulary, typed (doc 13)
- Gate P1 platform-preflight class (doc 17 §41.3)
- Data-classification tags check (doc 18 §49.3)
- This CHANGELOG (doc 10)
