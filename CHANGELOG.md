# Changelog

SemVer over the enumerated contract surface (CONTRIBUTING.md). One entry
per release, newest first; the git tags v0.8.0–v0.27.0 predate this file
and are summarized in the README roadmap and docs/implementation-map.md.

## v0.53.0 — renamed to ai-venture-studio; English is the UI default
- **Repository renamed** melodygaoyifan/ai-product-autopilot →
  **ai-venture-studio**. Live references updated (pyproject URLs, README,
  launch post, design canon links). GitHub redirects the old URLs, so
  existing clones and links keep working.
- **Recorded evidence was NOT rewritten.** The Gate PL5 and experiment-run
  records cite `gh api repos/…/ai-product-autopilot` with a `retrieved_at`:
  those are evidence snapshots, and an evidence snapshot is not edited after
  the fact (the same rule that makes the attention log append-only). Each now
  carries a note that the repo was renamed on 2026-07-27 and that
  re-measurements use the new name.
- **English is now the Studio default** (`DEFAULT_LANGUAGE = "en"`). The UI
  began Chinese-first because its first users were 小程序 founders; the repo
  is public and English-speaking, so the default now matches the audience
  that meets it first. `--lang zh` restores the original bilingual UI
  character for character — the strings were not touched, only the default —
  and a test asserts exactly that so the move is not a quiet degradation.
- The FDR template follows the same default, and the Chinese-founder tests
  now ask for `lang="zh"` explicitly rather than relying on a default, with
  new tests covering the English default path end to end.
- The package and CLI are still named `autoproduct`: renaming those would
  break every existing install, and that is a separate decision.
- Suite: 1068 -> 1071 hermetic tests

## v0.52.0 — the Studio speaks English, and the README demo shows it
- `autoproduct studio --lang en` renders the entire flow in English. Every
  user-facing string moved to `studio_i18n.py` keyed by language, and the
  FDR template gained an English twin asking the same six questions.
- **What made this necessary:** the README's founder demo claimed an
  English-or-Chinese product while the screenshot showed
  `写下你的产品需求 / Describe your product` — the UI was bilingual
  Chinese-first with no way to opt out. A demo that claims English and shows
  Chinese is a false claim about the product, not a cosmetic gap.
- `zh` (the default) keeps the original bilingual strings character for
  character, and a test asserts an unset language renders byte-identically
  to before. Existing users see no change; the flag is additive.
- An unknown language falls back to the default rather than rendering blank
  labels: a working UI in the wrong language beats a broken one in none.
  Codes normalise, so `EN`, `en-US`, `en_GB` all work.
- The README founder section is now English-first — web profile, an English
  FDR shown inline as the actual input, and a REAL screenshot of the real UI
  captured through Playwright at `docs/media/studio-en.png` (not a mockup;
  the Chinese screenshot stays linked for 小程序 founders). A test pins the
  README, the flag, and the image together so the demo cannot drift from the
  product again.
- Also honest now: the profile list in the README names all five profiles
  rather than three, and glosses the WeChat terms in English.
- Suite: 1060 -> 1068 hermetic tests

## v0.51.0 — a second kill-criterion axis, chosen by the human, evaluated by the machine
- The launch PRD now carries TWO axes. The new one (O-L2, capability
  regression) fires if the product-bench build rate falls below 60% OR the
  probe pass rate below 50% for 2 consecutive weekly runs.
- **Why this axis and not another:** its series already exists.
  `benchmarks/results/*.yaml` records build/probe/clean rates per run and the
  cadence is weekly, so this criterion can fire on the NEXT run — while the
  attention axis cannot fire until four consecutive weeks are logged. A
  second axis that also cannot fire would have added no coverage.
- **The floors are read, not chosen.** Runs 4-5 sat at 8-33% build, runs 6-9
  climbed 42-72%, runs 10-11 hold 74-75%. 60/50 sits below the current level
  and above the pre-fix era: crossing it means regressing into territory the
  system already climbed out of once. Two runs rather than one because at
  n=4 cases a single dip is noise, and a criterion that cries wolf gets
  ignored.
- `autoproduct bench-criterion` evaluates it, and `autoproduct loop` now
  reports both axes with their real readings in one line. Either firing
  demands a recorded human decision at Gate PL5 (invariant 14.20); neither
  evaluator decides.
- metrics/product_bench_capability.md defines the series, its exclusions
  (harness-noise runs, corpus changes that reset comparability), and its
  falsifier.
- **The PRD linter caught me:** the outcome instrumented
  `product_bench.run_recorded` while the metric counts
  `product_bench.case_built`, so P4 would have read zero. That is precisely
  the class of bug prd_lint exists for, and it fired on its own author.
- Suite: 1048 -> 1060 hermetic tests

## v0.50.0 — `loop` and `attention` now answer one question together
- `autoproduct loop` reads the attention streak, so the v3.0.0 gate report
  states the real distance to firing ("2/4 consecutive logged weeks over
  4.0h; 2 more would fire it") and the real next action ("log last week:
  `autoproduct attention --week 2026-W31 …`") instead of a static "the
  criteria need data that does not exist yet". Two commands shipped in
  separate releases were leaving the operator to join them by hand.
- A `not_tracked` row is reported as itself: it is a RECORDED decision, not
  a gap, so `loop` says the run "starts from the next week you log" rather
  than claiming last week is logged (which the first cut did) or asking for
  a rewrite of the record.
- When the criterion has fired, the next action becomes the decision —
  and the gate still does not close on it. Only a recorded human
  kill-or-pivot does (invariant 14.20), which the existing tests keep true.
- Absent log: the static wording, unchanged. Unreadable log: reported as
  unreadable rather than as a streak of zero.
- Suite: 1043 -> 1048 hermetic tests

## v0.49.0 — the use-case matrix, and the gap it found
- New `tests/test_use_case_matrix.py` tests the canon's coverage CLAIMS as a
  matrix instead of trusting that each part works because its own unit test
  passes: five domain profiles spec-and-build end to end, three editions
  resolve and lint narrowing-only, and the five-rung substrate ladder
  activates exactly the stages its floors allow.
- **The gap it found:** `STAGE_FLOORS` declared floors for eight stages, but
  only `code_review` and `deploy_review` ever consulted them. So doc 18's
  "stages below their infrastructure floor are inactive-never-degraded"
  (ADR-U15) was unenforced for six stages — an S0 team with no git could run
  `build`, and `triage` ran with no observability configured. discover,
  plan, spec, build and triage now enforce their floors with the same
  exit-code-4 refusal, and both directions are pinned: refused BELOW the
  floor, and never refused AT it (a guard that blocks legitimate work is
  worse than no guard).
- Recorded rather than smoothed over: `deploy_review` is the designed
  exception — above S0 it DEGRADES to config-lint-only instead of going
  inactive, because a config lint still helps without progressive delivery.
  A test pins that too, so the asymmetry stays deliberate.
- An absent `.mas/substrate-profile.yaml` still gates nothing, so no
  existing workspace starts refusing work because this exists.
- Suite: 1012 -> 1043 hermetic tests (+3 skips: stages with an S0 floor have
  no rung below them to be refused at)

## v0.48.0 — upstream resume, grounding at the spec writer, and the plan closed out
- **Upstream resume (gap-plan item 15's second half).** A task is the
  expensive unit upstream — spec + build + review, minutes and real money
  each — so autopilot now persists each outcome AS it completes and a re-run
  skips tasks already built on disk. Honestly labelled: this is
  task-granular, not super-step-granular like the review graph. A task
  interrupted halfway restarts that task; the ones before it stay done.
- `outcomes.yaml` is treated as a record, not an authority: an outcome
  claiming `built` is honored only when `built_task_ids` agrees the spec is
  actually built. A stale record can never make a run skip work that is not
  there.
- **Grounding now gates the SPEC writer too**, not just the build writer —
  the v0.42 asymmetry was arbitrary. Same finding as last time, one stage
  earlier: the spec writer never saw CLAUDE.md or the module invariants, so
  it could author a criterion contradicting an invariant, producing a build
  that cannot satisfy both and a SPEC_DRIFT flag against work nobody could
  have got right. Both now reach the prompt verbatim, and a spec authored
  blind to them raises rather than returning a weak spec.
- docs/gap-closure-plan.md reflects reality: every phase closed, item 15
  marked with both halves and their differing guarantees, and the
  "recorded non-goals" list corrected where later ADRs reversed it.
- Suite: 1008 -> 1012 hermetic tests (one end-to-end resume example, not a
  battery)

## v0.47.0 — the bot fleet: the game profile's last unbuilt check
- `autoproduct botfleet` runs N parallel bot sessions and triages what they
  hit: crashes, softlocks, unreachable-state regressions, out-of-bounds
  positions, and errors. Findings dedupe by signature across sessions and
  each carries a reproduction command — a bug a fleet found that cannot be
  replayed by hand is not actionable.
- **The design decision that made this shippable without an engine:** the
  fleet is defined by a session PROTOCOL (newline-delimited JSON events), not
  by a game. So the detectors are real functions over a real stream, verified
  against real subprocess sessions of a real deterministic simulation
  (`benchmarks/botfleet/toy_sim.py`, which is also the reference emitter an
  engine adapter copies). Wiring Unity or Unreal is now an adapter, not a
  redesign — and that adapter is the honest remaining open item.
- **Bug the first real run found:** one escaping bot produced 44 findings,
  because the out-of-bounds signature included the per-tick state hash. A
  continuing condition is now one finding per session, and the signature
  names which axis and side left the play area rather than how far along it
  the bot got. This is exactly what a stubbed stream would not have shown.
- Honest by construction elsewhere too: a hung session is a crash rather
  than a hang, a non-zero exit with no crash event is still a crash, an
  unconfigured or unrunnable command is a VISIBLE skip ("never counted as a
  clean overnight run"), and an undeclared netem profile is an error naming
  the declared ones.
- Scope, per §45.1: the fleet finds crashes and stuck states. A clean report
  says so explicitly — whether the game is FUN is the human playtest gate's
  question, and no bot replaces it.
- Suite: 982 -> 1008 hermetic tests

## v0.46.0 — the attention collector: making the v3.0.0 criterion able to fire
- `autoproduct attention` measures the OBSERVABLE FLOOR of weekly
  maintenance attention from ledgers `.mas/` already writes — gate dwell
  (escalate→final, the same measurement the rubber-stamp detector uses),
  recorded product-gate decisions, sweep reviews — and prints it with the
  artifacts it came from.
- **The machine never sets `hours`.** A floor is not a total: reading a
  review without touching a gate, thinking, and answering questions all
  count toward attention and leave no timestamp. So `hours` and
  `status: logged` stay human, `--by` is required (a number in this series
  has an author), and the floor is recorded BESIDE the human's number rather
  than instead of it.
- Append-only, enforced: an existing week is never rewritten, the log's
  header comment survives appends, and a malformed log errors rather than
  starting a fresh one.
- The streak reader implements the log's own rule — an untracked week breaks
  a streak without counting either way, and exactly-at-budget is not over
  budget. When four consecutive logged weeks exceed the budget the command
  exits 3 and says Gate PL5 now needs a recorded human decision. It does not
  make one.
- Why this was engineering worth doing: the v3.0.0 blocker was never "wait
  four weeks", it was that logging was a manual habit whose lapse silently
  reset the clock the criterion depends on. The habit is now cheap; the
  decision stays yours.
- Suite: 961 -> 982 hermetic tests

## v0.45.0 — the deploy-side CLI wrappers complete the §17.2 table
- terraform_validate, helm_lint, kubectl_dry_run, argocd_app_diff,
  flagger_inspect, railway_inspect join the L1 `deploy` partition. This is
  the table's other integration shape: BINARIES gated on being installed,
  following the pattern tools/external.py set for the scanners — an absent
  binary is a visible skip with the install hint, never counted as clean.
- `kubectl_dry_run` defaults to `--dry-run=client`, which never contacts a
  cluster. Server-side dry-run is real admission validation and more
  useful, but it talks to whatever cluster the current kubeconfig points
  at, so it is opt-in per call. A deploy review that silently reached into
  production because a context happened to be current is exactly the
  surprise this design spends its budget avoiding.
- Read-only is structural, not documentation: no wrapper names sync,
  rollback, up, redeploy, patch, delete, or destroy, and `apply` appears
  only behind `--dry-run` — asserted against the module's own source.
- Semantics that matter: argocd exits 1 when a diff EXISTS, so that is
  findings rather than an error, while auth failures and missing apps are
  errors; flagger flags unhealthy canaries but never patches one, because
  promoting or aborting a canary is a human's call.
- **Bug the tests found:** terraform with no parseable verdict (typically an
  uninitialized directory) reported "findings: 0 diagnostic(s)", which reads
  like a pass. A non-answer is now an error naming the likely cause.
- migration_dryrun from the §17.2 table was already covered by
  lanes.delivery.migration_rehearsal, so it was not duplicated.
- Honest scope: hermetic via a stubbed subprocess boundary. None has run
  against live infrastructure from this repo (no cluster, no cloud
  credentials); first real invocation per tool stays an open item.
- Suite: 932 -> 961 hermetic tests

## v0.44.0 — all six §17.2 signal readers, over one shared core
- datadog_query_metrics, pagerduty_get_incident, prometheus_query,
  loki_query, jaeger_query_trace join sentry_get_issue in the L1
  `maintenance` partition. Sentry's shape became a shared read-only core
  (gating, `secret://` resolution, GET-with-no-body, summarize, wrap,
  multi-secret scrub, errors-as-data), so each reader is its endpoint and
  its summary and nothing else.
- **Two gating families, deliberately distinguished.** A hosted service is
  gated on its credential; a self-hosted one on its base URL, because there
  is no sensible default address for a Prometheus and defaulting to
  localhost would turn "not configured" into a confusing connection error.
  Either way, unconfigured means a visible skip naming the exact variable.
- Details that are the point rather than decoration: Datadog requires BOTH
  keys and an explicit window (a metric read whose window nobody stated is
  not evidence); PagerDuty is read-only so it cannot ack, resolve, or
  reassign — the on-call human owns those; Loki's limit is bounded and its
  log lines get the same wrapper as everything else, which matters most
  there because log lines are the most user-influenced text in the stack;
  both Datadog keys are scrubbed from one payload.
- Honest scope, unchanged: written against each vendor's documented REST API
  and exercised against a stub transport. None has run against a live
  account from this repo — no credentials exist here — and the map says so
  per tool.
- Suite: 908 -> 932 hermetic tests

## v0.43.0 — the first external-service tool: sentry_get_issue
- maintenance/signals.py: reads one Sentry issue over the documented REST
  API, served by the L1 `maintenance` MCP partition. Adding it needed a row
  in the partition table plus a reader module — no transport, host, or RBAC
  change, which is what v0.40 claimed and this checks.
- House rules, all enforced by test: the credential is `AUTOPRODUCT_SENTRY_TOKEN`
  (raw or a `secret://ENV` ref through the v0.31 layer) and a configured-but-
  unresolvable ref errors rather than going unauthenticated; no token is a
  VISIBLE skip naming the env var, never an empty result, because "never
  asked" must not read like "nothing found"; the reader is read-only (the
  request builder sends no body and names no write verb, asserted on its
  source); the payload arrives `wrap_research`-wrapped, so a hostile issue
  title is data and consuming it taints the run out of L1+ (ADR-U03).
- Wired end to end: the Sentry webhook now passes the issue id through as
  `external_id`, and the maintenance graph gained a `signal` step that
  enriches a Sentry-sourced incident before root-cause analysis and records
  the wrapped payload in the mirror. A manual incident never calls out.
- **Bug the suite found:** substring-scrubbing the token shredded any payload
  containing its characters — with a 1-character token, everything. Scrubbing
  now has a length floor, because mangling a payload is worse than not
  scrubbing a string too short to be a credential.
- Honest scope: exercised hermetically against a stub transport. It has NOT
  been run against a live Sentry org here — no credential exists in this
  repo to do that with, and the module docstring says so instead of implying
  coverage it lacks.
- Suite: 891 -> 908 hermetic tests

## v0.42.0 — grounding enforced on every build, and the gap it found
- The Context Manifest is now wired into the build writer, not just
  available: every build assembles a manifest, records it at
  `.mas/manifests/<slug>.yaml`, and BLOCKS when a required entry's content
  never reached the implementer's prompt. Overflow blocks too, reported as
  a Planning split proposal rather than trimmed.
- Receipts for pushed context: `grounding_receipts` probes the prompt for
  each entry's most distinctive line instead of trusting a model's
  self-report. This checks assembly, not attention — it cannot prove the
  model read what it was handed, and the docstring says so.
- **The gap it found on the first run:** module-spec invariants
  (`.mas/specs/*.spec.yaml`) were never in the implementer's prompt, even
  though Code Review enforces them and flags SPEC_DRIFT_UNDOCUMENTED. The
  implementer was being held to a contract it had not been shown.
  Invariants and forbidden side effects now ship in the prompt, quoted
  VERBATIM — the probe requires the contract text itself, and paraphrasing
  a contract into a prompt is the smell the check exists to catch.
- Modeling correction: `spec.md` renders `spec.yaml` for a reader, so it is
  optional rather than a second obligation; requiring both fired a
  violation over a heading the machine contract never had.
- Suite: 886 -> 891 hermetic tests

## v0.41.0 — the ContextAssembler and research-session taint isolation
- upstream/context_assembler.py (§13.25.2, §13.29.3, §13.35.5): builds a
  task's Context Manifest deterministically under a token cap — spec slice
  first, code neighborhoods last, every entry content-hashed. Three
  mechanisms that only work together:
  * grounding receipts — `verify_sources_read` checks a writer's
    `sources_read` against the manifest; unread required context, a hash
    mismatch, or a claimed read of something unlisted are CONTRACT
    violations (§11.18.3), not quality notes;
  * drift detection — re-hashing catches a human editing a frozen artifact
    mid-flight, and `run_build` now refuses to build an unratified fork,
    naming the retro-SCR path instead of fighting the human (Gate U3
    pins a contract hash at approval; specs approved before v0.41 have no
    receipt and are treated as clean);
  * overflow as a planning defect — a task whose REQUIRED context exceeds
    the cap returns TASK_BLOCKED_CONTEXT_OVERFLOW with a split proposal
    rather than quietly compressing the contract.
- harness/taint_guard.py (§13.31.2, ADR-U03): the session-level enforcement
  the taint classes always assumed. `wrap_research` marks fetched content as
  data (and neutralizes a nested closing tag, so hostile content cannot
  close the wrapper and speak as the host); a run that consumes research is
  tainted one-way and loses L1+ tools for the rest of its life. Enforcement
  sits at the MCP transport where v0.40's risk tiers live, so the denial
  does not depend on anything the model says: L0 reading still works, L1/L2
  and unclassified tools are refused, and the refusal lands in the audit
  ledger. Taint arrives from tool OUTPUT, not declaration.
- Suite: 866 -> 886 hermetic tests

## v0.40.0 — the L1/L2 MCP partitions + the deploy-branch fix
- Three more partitions from doc 11 §17.2, for the tools that exist:
  `deploy` (L1: migration/workflow/canary probes), `maintenance` (L1:
  recent_commits, correlate), `test_exec` (L2: run_tests, which executes
  repo code — §17.2's reason for isolating it hardest). Five real servers
  now; the table's external-service tools (terraform, sentry, datadog)
  stay unbuilt and named as open rather than stubbed.
- Risk-tier RBAC at the transport: each partition declares L0/L1/L2 and
  MCPHost refuses to mount one above the caller's `risk_ceiling`, so a
  read-only voter cannot reach L1/L2 even if a future skill names one of
  their tools — enforced where the connection is made, not in a prompt.
  `MCPToolBox` also intersects with the L0 registry, so a voter allowlist
  cannot grow into stage tools by accident.
- Audit coverage now includes the tools that touch the most: deploy probes
  and test execution were previously unaudited.
- Fix (v0.39 follow-up): the deploy review now records the branch it
  covers (PR head branch, or the checked-out branch for a local range;
  empty on detached HEAD). `deploy-execute` and `automerge` treat an
  unresolvable branch as a REFUSAL — the old `or "main"` fallback would
  have let an armed policy act on work it was never armed for.
- Suite: 856 -> 866 hermetic tests

## v0.39.0 — policy-armed merge and deploy execution (ADR-031)
- `autoproduct automerge <review-id>` and `deploy-execute <id>`: the
  capabilities the README listed as out-of-scope now exist, DISARMED. A
  human arms them per repository in `.mas/automerge-policy.yaml` /
  `.mas/deploy-exec-policy.yaml`; the system's job is to refuse unless
  every declared condition mechanically holds.
- The bounding, which is the actual work: absence is never permission
  (`enabled: false` is the default inside a present file too); branch
  globs are refused so a policy cannot arm what it does not name;
  `armed_by` and `expires_at` are required and an expired policy is a hard
  error; a minimum track record of correct recommendations must exist
  before the first automated action; only APPROVE/APPROVE_WITH_NOTES may
  precede a merge and an escalated review's decision stands; migrations,
  IaC, Dockerfiles, CI workflows, k8s/Helm, CLAUDE.md, `.mas/`, and the
  policy files themselves always demand a human — so automation can never
  widen its own permissions; `deploy-execute` runs only the exact argv a
  human wrote, never one the system composes; no `--admin` escape, so
  branch protection wins.
- `.mas/automation-log.jsonl` records actions AND refusals with reasons:
  "why didn't it merge" deserves the same answer quality as "why did it".
- CLAUDE.md's invariant revised to match the code, and ADR-031 records the
  reversal with its mechanism. Auto-hotfix stays out entirely.
- Suite: 817 -> 856 hermetic tests (36 of the 39 new ones assert refusals)

## v0.38.0 — multi-tenant server mode (ADR-030) + the ADR directory
- One `serve` process may now front several isolated workspaces:
  `.mas/tenants.yaml` maps a tenant id to a SHA-256 token hash and a
  workspace root; `autoproduct tenant add|list` manages it and prints the
  plaintext token exactly once.
- Isolation is the mechanism, not the aspiration: workspaces must be
  disjoint (a root contained in another fails at LOAD time), the token
  picks the workspace and no client-supplied path or id ever does,
  per-tenant GitHub secrets are `secret://ENV` references so one tenant's
  secret cannot verify another's deliveries, read routes (/jobs, /reviews)
  require the token in multi-tenant mode, and unknown/disabled/missing
  tokens answer identically so responses never enumerate tenants.
- Security fix found on the way: `review_id` was interpolated into a
  filesystem path unvalidated. Now `[A-Za-z0-9_-]{1,64}` — in multi-tenant
  mode that was a traversal into a neighbour's workspace.
- Single-tenant mode is byte-for-byte unchanged: no registry, no
  multi-tenancy, shared-secret path and open localhost reads as before.
- docs/adr/: the implementation's own decision records, starting with the
  three that REVERSE a recorded non-goal (029 MCP transport, 030
  multi-tenant, 031 policy-armed automation). A scope reversal that lives
  only in a commit message is indistinguishable from scope creep. Closes
  the map's "ADR docs" open item.
- Still out: SaaS — billing, plans, quotas, a shared database, a hosted
  control plane, per-tenant key management. Tenants bring their own keys.
- Suite: 795 -> 817 hermetic tests

## v0.37.0 — MCP as the internal tool transport (doc 11 §17), first real slice
- autoproduct/mcp/: JSON-RPC 2.0 over stdio (newline-delimited), two real
  partitions from doc 11 §17.2 — read_only (read_file/grep/list_files) and
  code_intel (symbol_refs) — each served by its own subprocess via
  `python -m autoproduct.mcp.server <name>`.
- The triple check made real (§17.3): the skill allowlist decides which
  tools exist, MCPHost mounts only the servers those tools live in (so an
  unlisted tool is unreachable, not merely refused), and the server itself
  refuses anything outside its partition. Any one layer's bug fails closed.
- Subprocess isolation is the property the in-process mapping could not
  give: a path-traversal attempt is now refused inside the child process.
- mcp-audit ledger (.mas/mcp-audit.jsonl): every call, permitted or
  refused, with voter, server, tool, digested args, outcome and duration.
  Arguments are digested rather than copied — the ledger records what was
  asked for without duplicating searched content.
- Transport switch: AUTOPRODUCT_TOOL_TRANSPORT=mcp opts in; in-process
  stays the default because a subprocess spawn per server per invocation
  should be paid deliberately. Both toolboxes present one surface, and the
  caller's budget stays authoritative.
- Still out, by design and named in the map: external MCP servers (doc 11
  §17.1's supply-chain reasoning), and the L1/L2 deploy/maintenance/
  test-exec partitions — two real servers beat eight stubs.
- Suite: 778 -> 795 hermetic tests

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
