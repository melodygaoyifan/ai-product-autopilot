# autoproduct

**Write one document. Get a working product.**

![License: MIT](https://img.shields.io/badge/license-MIT-green) ![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue) ![Tests](https://img.shields.io/badge/hermetic_tests-~190-brightgreen)

One plain-language paragraph in — a planned, built, tested, reviewed product out:

```text
FDR.md — written by a non-technical founder, in their own words:

  小区团购接龙的后端 API(先只做后端)。
  团长能创建一个团购(商品名和单价),能查看它;
  住户能对某个团购下单(名字和数量);
  团长能看到某个团购的汇总(总件数、应收总额)。
  数据要存在数据库里,重启不丢。暂时不要:页面、支付、登录。
```

&nbsp;&nbsp;&nbsp;&nbsp;↓ &nbsp;`autoproduct create groupbuy --profile web`

- ✅ **开工前确认** — the plan read back in plain language *before* anything is built
- ✅ **Locked task DAG** — cycle/lane/budget-checked; scope changes only via approved SCR
- ✅ **Machine-linted acceptance criteria** (EARS) — each one covered by a test skeleton
- ✅ **Working code + hermetic tests** — test-first, sandboxed suite must pass
- ✅ **6-voter code review** — deterministic security probes, every finding independently verified
- ✅ **Build report in your language** — every automated approval on the record

*(All of the above are real artifacts from one run — see [A real run](#a-real-run-unedited) below.)*

<!-- TODO: terminal GIF of `autoproduct studio` / `create` goes here (vhs or asciinema) -->

autoproduct builds apps, web services, and 微信小程序 from a single
requirements document (the **FDR**) written by someone with **no coding or
product experience** — in their own words, in their own language. The
system coaches you until the FDR is buildable, confirms the plan back in
plain language, then designs, implements, tests, and reviews the product
through a multi-agent pipeline with every automated decision on the record.

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

## What happens under the hood

Eight-stage multi-agent pipeline (design docs:
[autoproduct-design](https://github.com/melodygaoyifan/autoproduct-design)):

**Upstream:** Discovery (evidence-tagged hypotheses — fabricating user
evidence is a schema violation) → Planning (task DAG with cycle/lane/budget
checks, calibrated estimates) → Spec (EARS criteria machine-linted, every
criterion covered by a test skeleton, frozen behind SCRs once built) →
Coding (single-writer, test-first, existing tests read-only with
AST-checked no-weakening, sandboxed suite must pass, optional parallel
lane worktrees).

**Downstream:** Code Review (6 heterogeneous voters with investigation
tools incl. a tree-sitter symbol index, deterministic probes for secrets/
CSRF-SSRF/slopsquatting/frontend↔backend wireup drift, every finding
independently verified) → Test Gate (isolated worktree, python + JS
runners, mutation testing in deep mode) → Deploy Review → Maintenance
(incident triage → root cause → fix-PRs whose regression tests must fail
pre-fix; human-approved learned skills).

Serious review findings trigger a bounded repair iteration. Crashed runs
resume from checkpoints (`autoproduct recover`). Two human-gated learning
loops compound: review signals → CLAUDE.md constraints; recurring
incidents → investigator skills.

**Gate philosophy:** humans keep the judgments they're best at (is this my
intent?); machines keep the ones non-technical users can't make (EARS
validity, DAG soundness, tests) — every auto-approval is recorded. Nothing
auto-merges, nothing deploys to production autonomously.

## A real run (unedited)

Everything below is generated output from one `autoproduct product-bench --real`
case — the group-buy FDR shown at the top of this page. Nothing is hand-edited.

**1. The system confirms the plan back in plain language (Gate U1/U2 — you reply `--yes`):**

> **会做什么**
> - 团长可以**创建一个团购**,填写商品名和单价,系统会返回一个团购的编号。
> - 住户可以**对某个团购下单**,填写自己的名字和购买数量。
> - 团长可以**查看某个团购的汇总**:一共订了多少件、总共应收多少钱。
> - 所有数据都会**保存在数据库里**,就算服务器重启,团购和订单也不会丢。
>
> **这次不做**
> - 登录和身份系统 · 支付和对账 · 任何网页界面 · 修改或取消订单 · 截止时间
>
> **怎么算成功**
> - 下单后,汇总的**总件数一件不差**;应收金额**一分不差**(单价 × 总件数)。
> - 服务器重启后,已创建的团购和订单**一条都不丢**。

**2. The locked plan (generated task DAG, Gate U2):**

| id | task | depends on | lane | est |
|---|---|---|---|---|
| t1 | 数据持久化基座与团购创建 | — | api | 6.0h |
| t2 | 查看单个团购详情 | t1 | api | 4.0h |
| t3 | 对团购下单 | t2 | api | 6.0h |
| t4 | 查看团购汇总 | t3 | api | 5.0h |

**3. What lands in the workspace** (built test-first, then reviewed):

```text
app/        main.py db.py store.py orders.py summary.py handlers.py
specs/      EARS acceptance criteria per feature + API contracts
tests/      16 test files — persistence, validation, 404s, summary math
product/    brief.md · plan.md · CONFIRMATION.md · ACCEPTANCE.md · BUILD-REPORT.md
```

Every built product is then scored by *independent* behavioral probes
(start the server, hit the API, check the math) — results are reported
unaveraged in the product benchmark, including the runs that fail.

## Measured

- **Review benchmark** (`autoproduct bench`): recall 100%, precision 67%
  on 13 labeled cases (bars: 40%/50%).
- **Product benchmark** (`autoproduct product-bench`): full FDR→product
  runs scored by *independent* behavioral probes executed against the
  built product ([WebGen-Bench](https://arxiv.org/abs/2505.03733)
  pattern) — build rate, probe pass rate, and clean-review rate reported
  unaveraged, with an honesty case proving probes can fail.
- ~190 hermetic tests (`uv run pytest`); every PR in this repo was
  reviewed by autoproduct itself, and five of those reviews caught real
  bugs in the features they were reviewing.

## For developers

| | |
|---|---|
| `discover / plan / spec / build` (+ `*-approve`) | upstream stages individually, gates U1–U4 |
| `scr` / `scr-approve` | the only legal way to change a built spec |
| `review` · `resume` · `recover` · `replay` | review pipeline, HITL, crash recovery, audit trail |
| `deploy-review` · `deploy-outcome` · `triage [--fix]` | Gates 5–6 |
| `serve` | webhook mode: PRs review themselves; incidents POST in |
| `worker` | queue worker — set `AUTOPRODUCT_QUEUE_DB` on `serve` and run N workers to drain bursts in parallel (SQLite, one host; multi-host needs a shared broker) |
| `bench` · `product-bench` · `compound --pr` | the two benchmarks + the compounding loop |
| `claim-lint` · `prd-lint` · `handoff-check` | outer-loop gates standalone (docs 20–23): claim ledgers, PRD boundary/kill-criteria/instrumentation, the machine-checked P2→Stage-1 handoff |
| `preregister` · `experiment-check` | pin an experiment design before exposure; preflight schema + FDR plan + power + pin integrity (§21.61) |
| `opportunity` · `market` / `market-approve` · `prd` / `prd-approve` · `evidence` | the outer loop as one-command stages: writer → det tools → charter voters → verify → leader → gate, human decisions recorded at PL1/PL2, handoff emitted and DoR-validated |

Setup: `uv sync`, `ANTHROPIC_API_KEY` (yours — keys live only in your
environment, are never written to the workspace or git, and every
provider errors loudly if its key is missing). `OPENAI_API_KEY` optional
but recommended: it puts a real GPT-5 in the security and deploy-config
voter seats, breaking same-family self-preference when Claude reviews
Claude-written code; without it those seats visibly fall back
(`substituted_from`). `GEMINI_API_KEY`/`XAI_API_KEY` optional likewise.
`gh` auth,
Docker optional (network-isolated test sandbox), Node optional (JS test
gate). Operations guide: [RUNBOOK.md](RUNBOOK.md).

## Honest limits (today)

- The outer product loop runs end-to-end (`opportunity` → `market` →
  `market-approve` → `prd` → `prd-approve` → `evidence`), but its release
  bar is honest: it is unproven until a real Gate PL5 records a real kill
  or pivot on a live cycle.
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
| v0.11 ✅ | traditional-industry adoption track |
| v0.12 ✅ | adoption hardening (degraded mode, dwell metric, profile wiring, evaluator graduation) |
| v0.13 ✅ | product-loop substrate (docs 20–23 weeks P1–P2): typed claim ledger, `claim_lint`, evidence snapshots, synthetic-persona scan, source standing, `user_data_taint` |
| v0.14 ✅ | safe-publish (weeks P3–P5): the seven deterministic marketing backstops, channel profiles, Gate PL3 scoped approvals, `forbidden_autonomous` additions — the framework drafts and checks, a human presses every publish button, and it never spends money |
| v0.15 ✅ | evidence (weeks P6–P8): analytics/feedback boundary with query-layer person-level refusal, metric vocabulary with baseline-resetting definitions, cohort readings with sufficiency teeth, P4/Stage-8 signal router, attribution typed at the tool boundary — only holdouts ground causal claims |
| v0.16 ✅ | upstream (weeks P9–P13): P0 opportunity sensing (deterministic clustering, kill-registry read path, Gate PL0), P1 market & viability (`sizing_calc` ranges not points, `injection_scan`, standing-checked probes, Gate PL1), P2 PRD (`prd_lint`, kill criteria required, instrumentation-or-task), and the machine-checked `p2_to_stage1` handoff validated at Discovery's DoR gate — plus 16 upstream voter charters |
| v0.17 ✅ | experiments (weeks P12–P14): hash-pinned pre-registration (post-hoc edits void the analysis), one primary metric, BH-controlled two-stage screening→validation, O'Brien–Fleming sequential peeking, guardrail vetoes, `BLOCKED(INSUFFICIENT_POWER)` as a supported outcome, and inconclusive-enters-nothing at the compounding boundary |
| v0.18 ✅ | closed loop (weeks P15–P16): `evaluate_kill_criteria` (a fired criterion cannot be closed without a recorded human decision), the append-only kill registry writer, hypothesis reconciliation with claim-ID invalidation, Gate PL5 (routes to P0/P1/P2, never the inner loop), and the five outer-loop metrics — including attention cost per resolved hypothesis, the number by which the whole product loop is falsifiable. Completes the docs 20–23 track at the deterministic layer; the v3.0.0 design gate closes with the operator's first real recorded kill-or-pivot |
| M2–M7 ✅ | screenshots of the built product (gated, visible when absent), in-Studio correction loop with SCR-backed scope changes, generated 验收清单 walkthrough covering every built criterion, built-in telemetry with digest reconciliation, 微信支付/登录/订阅 blocks catalog, estimate hints + checkpoint undo |

## Star history

[![Star History Chart](https://api.star-history.com/svg?repos=melodygaoyifan/autoproduct-ai&type=Date)](https://star-history.com/#melodygaoyifan/autoproduct-ai)

---

MIT · design docs: [autoproduct-design](https://github.com/melodygaoyifan/autoproduct-design)
