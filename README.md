# autoproduct — AI product autopilot

**Finds what to build from your real signals. Sizes it honestly. Writes the
PRD. Builds, tests, and reviews the product. Measures whether it worked —
and forces the kill decision when it didn't.**

![License: MIT](https://img.shields.io/badge/license-MIT-green) ![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue) ![Tests](https://img.shields.io/badge/hermetic_tests-595-brightgreen)

A week of real product signals in — an evidence-gated product decision out:

```text
signals.yaml — support tickets + GitHub issues, verbatim:

  s1  "I started a build and stared at the terminal for 40 minutes with
       no idea whether it was progressing or stuck"
  s3  "show live build progress per task in studio — right now it looks
       frozen while it works"
  s4  "can I send a preview of the built product to my cofounder, a link
       she can open on her phone"
  s6  "how much will a typical month of builds cost me? I'm scared to
       leave autopilot running"
```

&nbsp;&nbsp;&nbsp;&nbsp;↓ &nbsp;`autoproduct opportunity signals.yaml` → `market` → `prd` → *(build)* → `evidence`

- ✅ **4 grounded candidates** (Gate PL0) — every claim cites its ticket verbatim; each carries a falsifiable hypothesis and a *named cheapest test* ("ship a clickable mockup to the 3 reporters", not "build an MVP")
- ✅ **A market assessment its own voters attack** — the Sizing seat caught an ungrounded 0.15 affected-fraction inference; the Competitive seat caught "no competitor does this" resting on a single pricing-page probe; the dedicated Disconfirmation seat argues the other side on the same evidence
- ✅ **A PRD with teeth** (Gate PL2) — three kill criteria authored *before* anyone is attached, the sibling candidates explicitly listed as non-goals, and a Planning task auto-generated for the metric nobody had instrumented yet
- ✅ **A machine-checked handoff** into the build pipeline — Discovery reads exactly the PRD that passed the gate, or nothing
- ✅ **An honest verdict** (Gate PL4) — panel-open rate read at **24.0% (n=250, CI 19.1–29.7%)** against a 30% kill threshold → `insufficient_evidence`: the interval brushes the line, so the system says "here's the n it would take to know" instead of declaring victory

*(Every artifact above is unedited output from one real-provider run — see
[A real run](#a-real-run-unedited) below.)*

<!-- TODO: terminal GIF of the opportunity → evidence chain (vhs or asciinema) -->

Two loops, one system. The **inner loop** builds: apps, web services, and
微信小程序 from a single plain-language requirements doc (the **FDR**) —
written by someone with no coding background, in their own words, English
or Chinese. The **outer loop** decides: it mines your owned signals for
opportunities, sizes markets bottom-up with mandatory sensitivity ranges,
writes PRDs with required kill criteria, measures real cohorts through a
privacy boundary, and routes every irreversible act — publishing, spending,
shipping, killing — to a named human at a recorded gate.

## For founders (no technical background needed)

```bash
autoproduct studio myshop --profile miniprogram    # browser UI: the whole flow
```

or the same flow in the terminal:

```bash
autoproduct create myshop --profile miniprogram    # 1. writes FDR.md template + guide
# ← fill in FDR.md in your own words (Chinese or English)
autoproduct create myshop --profile miniprogram    # 2. asks questions OR confirms the plan
autoproduct create myshop --profile miniprogram --yes   # 3. builds everything
autoproduct preview                                # 4. try your product
autoproduct add feature.md --yes                   # 5. one small FDR per new feature
autoproduct ship                                   # 6. deploy artifacts + plain-language guide
```

- **If your FDR is unclear, the system asks — it never guesses** (at most
  5 questions a non-technical person can answer, in your language).
- **One FDR = one thing.** The first FDR is the smallest usable product;
  every later feature is its own small FDR via `add`. Granular builds are
  more accurate and fail more debuggably.
- **You confirm intent in plain language** before anything is built, and
  get a build report in your language after — including every automated
  approval the machine made on your behalf.
- **Real persistence out of the box**: a local SQLite database is
  provisioned automatically; cloud services (Supabase, 微信云开发) are a
  guided option with credentials in a vault that never enters prompts.
- Profiles carry domain rules: 小程序 (2MB package budget, domain
  whitelist, lazy 授权 with 隐私协议, WeChat review boundaries), web
  (CSRF/SSRF, a11y, E2E flows), app (store rules, offline behavior).

## For product decisions (the outer loop)

```bash
autoproduct opportunity signals.yaml         # P0: cluster real signals → candidates, Gate PL0
autoproduct market cand-x --evidence probes.yaml   # P1: bottom-up sizing, six voters incl. Disconfirmation
autoproduct market-approve --outcome pursue --scope-tier thin --decider you   # Gate PL1 (human)
autoproduct prd                              # P2: PRD with kill criteria, planning tasks generated
autoproduct prd-approve --decider you        # Gate PL2 + machine-checked handoff into the build
autoproduct evidence events.yaml --metric build_progress_view_rate --cohort-start 2026-07-10
```

The rules that make it trustworthy are structural, not aspirational: every
quantitative claim is typed and machine-linted (`claim_lint` — unsourced
numbers, causal-language-without-a-holdout, and missing falsifiers fail the
gate); agents may never author a user quote or persona; sizing is a range,
never a point; person-level data cannot leave the analytics boundary (the
query errors); experiments are hash-pinned before exposure; the framework
never publishes, sends, or spends autonomously; and a fired kill criterion
cannot be closed without a recorded human decision.

## What happens under the hood

Fourteen gated stages across two loops (design docs:
[autoproduct-design](https://github.com/melodygaoyifan/autoproduct-design)):

**Outer loop (weeks-to-months):** Opportunity sensing (deterministic
clustering of owned signals, kill-registry memory) → Market & viability
(standing-checked probes, `injection_scan` over snapshots, a red-team
Disconfirmation voter) → PRD (kill criteria required at authoring time) →
… → Product evidence (cohort reads through a k-anonymity boundary,
attribution typed at the tool boundary) → Portfolio (mechanical
kill-criteria evaluation, append-only kill registry).

**Inner loop, upstream:** Discovery (evidence-tagged hypotheses —
fabricating user evidence is a schema violation) → Planning (task DAG with
cycle/lane/budget checks) → Spec (EARS criteria machine-linted, every
criterion covered by a test skeleton, frozen behind SCRs) → Coding
(single-writer, test-first, AST-checked no-test-weakening, sandboxed suite
must pass).

**Inner loop, downstream:** Code Review (6 heterogeneous voters,
deterministic probes for secrets/CSRF-SSRF/slopsquatting/wireup drift,
every finding independently verified) → Test Gate (isolated worktree,
mutation testing in deep mode) → Deploy Review → Maintenance (triage →
root cause → fix-PRs whose regression tests must fail pre-fix).

Every generative stage runs the same template: one writer, deterministic
tools first, independent charter voters (each fixture-gated at 8 cases,
≥87.5% to register), a fresh verify pass per finding, a leader synthesis,
and a gate — human wherever judgment is the point. Nothing auto-merges,
nothing deploys autonomously, nothing publishes, nothing spends.

## A real run (unedited)

Everything below is real-model output from one end-to-end run of the
opportunity chain (`opportunity` → `market` → `prd` → `evidence`) on the
signals shown at the top of this page. Signal texts and competitor-probe
pages are fixtures; every judgment, artifact, and number below was produced
by the pipeline, unedited.

**1. P0 turns four signals into grounded candidates (Gate PL0 passed):**

> **cand-build-progress** — Users cannot tell whether an in-progress build
> is advancing or stuck, so they need live per-task progress visibility.
> - hypothesis: live per-task progress stops long builds reading as frozen
> - falsifier: a prototype does not reduce "is it stuck?" reports
> - cheapest test: *ship a clickable mockup to the 3 ticket reporters and
>   count how many confirm it resolves their "frozen" uncertainty*

**2. P1's own voters attack the market case (three verified majors):**

> "…the revenue sizing hinges on an ungrounded 0.15 affected-fraction
> inference multiplied against the real 900-workspace base, the
> price-headroom positioning rests on only two vendors, and the Vendor B
> absence claim relies on a single pricing-page probe rather than a proper
> probe list."

The deterministic gate had already blocked an earlier draft outright: 75%
of its claims were `model_inference` against the 30% market ceiling —
reasoning dressed as research doesn't pass.

**3. P2 writes a PRD with its own death spelled out (Gate PL2):**

> - kill: *"fewer than 3 of 3 mockup reporters confirm it resolves their
>   'frozen' uncertainty"*
> - kill: *"build_progress_view_rate stays below 30% after 30 days"*
> - non-goals: the sibling candidates, by name (shareable previews, cost
>   visibility, dark mode)
> - generated Planning task: *instrument `build_progress_panel_viewed` so
>   O-1 is measurable before launch*

**4. P4 reads the cohort and refuses to flatter it (Gate PL4):**

```text
build_progress_view_rate: 0.240   n=250   CI [0.191, 0.297]   window complete
verdict H-1: insufficient_evidence — the interval brushes the 30% kill
threshold; the honest output is the n it would take to know, not a win.
```

The same machinery runs the other direction too: the inner loop's product
benchmark (`product-bench`) builds full products from plain-language FDRs
(English or Chinese) and
scores them with independent behavioral probes, reported unaveraged —
including the runs that fail.

## Measured

- **Review benchmark** (`autoproduct bench`): recall 100%, precision 67%
  on 13 labeled cases (bars: 40%/50%).
- **Product benchmark** (`autoproduct product-bench`): full FDR→product
  runs scored by *independent* behavioral probes executed against the
  built product ([WebGen-Bench](https://arxiv.org/abs/2505.03733)
  pattern) — build rate, probe pass rate, and clean-review rate reported
  unaveraged, with an honesty case proving probes can fail.
- **595 hermetic tests** (`uv run pytest`); every PR in this repo was
  reviewed by autoproduct itself, and five of those reviews caught real
  bugs. The first live smoke of the outer loop surfaced three wiring bugs
  — each caught by a gate doing its job, each now a regression test.

## For developers

| | |
|---|---|
| `opportunity` · `market` / `market-approve` · `prd` / `prd-approve` · `evidence` | the outer loop as one-command stages: writer → det tools → charter voters → verify → leader → gate; human decisions recorded at PL1/PL2 |
| `voter-gate <stage>` | register voters against their 8-fixture gates (≥87.5%); failed voters stop voting |
| `claim-lint` · `prd-lint` · `handoff-check` | outer-loop gates standalone: claim ledgers, PRD boundary/kill-criteria/instrumentation, the machine-checked P2→Stage-1 handoff |
| `preregister` · `experiment-check` | pin an experiment design before exposure; schema + FDR plan + power + pin integrity |
| `discover / plan / spec / build` (+ `*-approve`) | inner-loop upstream stages, gates U1–U4 |
| `scr` / `scr-approve` | the only legal way to change a built spec |
| `review` · `resume` · `recover` · `replay` | review pipeline, HITL, crash recovery, audit trail |
| `deploy-review` · `deploy-outcome` · `triage [--fix]` | Gates 5–6 |
| `serve` · `worker` | webhook mode + queue workers (SQLite, one host) |
| `bench` · `product-bench` · `compound --pr` | the two benchmarks + the compounding loop |

Setup: `uv sync`, `ANTHROPIC_API_KEY` (yours — keys live only in your
environment, are never written to the workspace or git, and every
provider errors loudly if its key is missing). `OPENAI_API_KEY` optional
but recommended: it puts a real GPT-5 in the security and deploy-config
voter seats, breaking same-family self-preference when Claude reviews
Claude-written code; without it those seats visibly fall back
(`substituted_from`). `GEMINI_API_KEY`/`XAI_API_KEY` optional likewise.
`gh` auth, Docker optional (network-isolated test sandbox), Node optional
(JS test gate). Operations guide: [RUNBOOK.md](RUNBOOK.md).

## Honest limits (today)

- The outer loop runs end-to-end and survived its first real-provider
  smoke, but its release bar is honest: it is unproven until a real Gate
  PL5 records a real kill or pivot on a live cycle.
- Cloud services are guided, not auto-provisioned; deploys generate
  artifacts + instructions, the button stays yours.
- 小程序 page-level testing needs `miniprogram-simulate` installed;
  pure-logic modules are gated via `node --test` today.
- Single-machine operation; crash recovery is per-review, Celery/Redis
  multi-instance supervision is the documented upgrade path.

## Roadmap

| | |
|---|---|
| v0.8 ✅ | all four downstream stage MASes (code review, test gate, deploy review, maintenance) |
| v0.9 ✅ | greenfield autopilot for non-technical founders (FDR → product) |
| v0.10 ✅ | founder experience complete + measured (Studio UI, product benchmark) |
| v0.11–v0.12 ✅ | traditional-industry adoption track + hardening |
| v0.13 ✅ | product-loop substrate: typed claim ledger, `claim_lint`, evidence snapshots, synthetic-persona scan, source standing, `user_data_taint` |
| v0.14 ✅ | safe-publish: the seven deterministic marketing backstops, channel profiles, Gate PL3 scoped approvals — a human presses every publish button, and it never spends money |
| v0.15 ✅ | evidence: analytics/feedback privacy boundary, metric vocabulary with baseline-resetting definitions, cohort reads with sufficiency teeth, attribution typed at the tool boundary — only holdouts ground causal claims |
| v0.16 ✅ | upstream P0–P2: opportunity sensing, market & viability, PRD with required kill criteria, machine-checked handoff into Discovery |
| v0.17 ✅ | experiments: hash-pinned pre-registration, two-stage FDR-controlled screening→validation, sequential peeking, guardrail vetoes, inconclusive-enters-nothing |
| v0.18 ✅ | closed loop: `evaluate_kill_criteria` (a fired criterion cannot close without a recorded human decision), append-only kill registry, hypothesis reconciliation, the five loop metrics |
| v0.19–v0.20 ✅ | the outer loop operable end-to-end: gate CLIs, then the four LLM stages as one-command runs; first real-provider smoke (three wiring bugs found by gates, fixed); 24 voter fixture-registration gates + `voter-gate` |
| M2–M7 ✅ | build screenshots (gated-visible), in-Studio correction loop with SCR-backed scope changes, 验收清单 walkthrough, telemetry + digest, 微信支付/登录/订阅 blocks, estimate hints + undo |
| next 🔜 | the v3.0.0 design gate: one live loop ending in a real recorded kill-or-pivot at Gate PL5 |

## Star history

[![Star History Chart](https://api.star-history.com/svg?repos=melodygaoyifan/ai-product-autopilot&type=Date)](https://star-history.com/#melodygaoyifan/ai-product-autopilot)

---

MIT · design docs: [autoproduct-design](https://github.com/melodygaoyifan/autoproduct-design)
