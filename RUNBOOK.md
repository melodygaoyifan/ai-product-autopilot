# autoproduct — operations runbook

Day-to-day operation of all four stages. Assumes `uv` and an
`ANTHROPIC_API_KEY` in the environment (other provider keys optional —
voters fall back visibly without them).

## Commands

| Command | What it does |
|---|---|
| `autoproduct review <PR-URL \| git-range>` | Code Review + Test stages (Gates 1–3) |
| `autoproduct resume <review-id> --decision ack\|override:<VERDICT>` | Continue a review paused at Gate 3 |
| `autoproduct deploy-review <target>` | Gate 5 — deploy recommendation (never deploys) |
| `autoproduct deploy-outcome <review-id> --outcome correct\|incorrect` | Record the human verdict; builds the trust-tier track record |
| `autoproduct triage <incident-file> [--fix]` | Gate 6 — triage + root cause; `--fix` approves a fix-PR attempt |
| `autoproduct replay [<review-id>]` | Audit trail of any past review |
| `autoproduct bench` | Regression benchmark (bars: recall ≥40%, precision ≥50%) |
| `autoproduct compound [--pr]` | Weekly signal aggregation → CLAUDE.md proposal |
| `autoproduct serve` | Webhook mode (needs `AUTOPRODUCT_WEBHOOK_SECRET`) |
| `autoproduct readiness` | Substrate-ladder report (docs 18–19): active stages at the declared rung, what each missing rung unlocks |
| `autoproduct evidence-bundle <review-id>` | Export the Gate-R evidence bundle (unsigned v0) for CAB/change-control submission |
| `autoproduct toolchain <language> [--manifest seeded.yaml]` | Run a language lane's det_tools slots (skipped = loud, never clean); with a seeded-defect manifest, measure catch-rate and register (or label PROVISIONAL) |
| `autoproduct calibrate <language>` | Calibrate seeded-lane patterns against real scanners; per-defect report with actual slot output for each miss (run via `make calibrate`) |
| `autoproduct eval-gate <scores.yaml> [--pin]` | Eval-set regression gate vs the pinned baseline; `--pin` re-baselines (commit the diff via PR) |
| `autoproduct idempotency <run_a> <run_b>` | Backfill idempotency: the fixture-slice re-run must be byte-identical |
| `autoproduct data-checks` | Run the workspace's external data checks (dbt auto-detected; others in `.mas/data-checks.yaml`) |
| `autoproduct attest [<review-id>]` | Chain a review's gate/verdict records into the hash-chained attestation ledger, then verify the chain |
| `autoproduct dwell` | Approval-dwell-time report (F-18.3): flags the rubber-stamp pattern (fast acks + zero overrides) |
| `autoproduct cab-package <review-id>` | Assemble a CAB change package (evidence bundle + prefill) and run the Gate-R preflight; humans complete rollback/approver and submit |

## Substrate ladder (traditional-industry adoption, docs 18–19)

Opt-in: declare `.mas/substrate-profile.yaml` (schema in §18.47.1) and
stages below their infrastructure floor refuse with `STAGE_INACTIVE`
(exit code 4) instead of running vacuously — `deploy-review` degrades to
config-lint-only from S1 and says so. No profile file = no gating
(effective S4, unchanged behavior). Gate R rejections are recorded with
`autoproduct.adoption.record_rejection` — mechanizable reasons become
preflight fixtures in `.mas/cab-preflight.yaml`, the rest land in
`.mas/cab-rejections.yaml` for the compounding loop. CAB submission
itself is human-only, always.

**Toolchain calibration (§19 G7).** The seeded-lane manifest patterns in
`tests/toolchains/seeded/{java,dotnet}/seeded.yaml` are hand-labels until a
real scanner run confirms them. `make calibrate` builds the
`Dockerfile.calibrate` image (Checkstyle, PIT, Semgrep, OWASP
Dependency-Check, Stryker, dotnet SDK) and runs `autoproduct calibrate` per
lane, writing per-defect reports to `.mas/calibration/<lang>.yaml` and a
`calibration-summary.md` roll-up. A **miss on a slot that ran** means the
pattern is wrong — fix it in the manifest using the slot output the report
captured; a **skipped slot** means the scanner is absent. Re-run on every
scanner version bump (R-G3). `make calibrate-local` runs it on the host if
the scanners are already installed.

## Weekly rhythm

1. `autoproduct compound --pr` — review and merge (or close) the proposal.
2. `autoproduct bench` — must PASS; a regression after merging a compound
   PR means Gate 4: revert the CLAUDE.md change.
3. Skim `.mas/voters/*/log.yaml` block rates; a voter blocking repeatedly
   is a prompt/tool problem, not noise.
4. Approve or delete any `status: proposed` files in
   `.mas/learned-skills/`.

## When a review escalates (Gate 3)

A GitHub Issue opens with the findings and a resume command. Decide:
- `--decision ack` — the verdict stands (it will block merge).
- `--decision override:<VERDICT>` — your call is recorded in the summary
  and `final.yaml`; the audit trail keeps both verdicts.

## Deploy trust tiers

Stage starts at `insight` (recommend only). After the configured streak of
correct PROMOTE marks (`promotion_track_record`, default 10), the summary
reports assistive-tier eligibility — graduating is your edit to
`.mas/deploy-policy.yaml`. Production deploys are never autonomous,
regardless of streak.

## Webhook mode

```
export AUTOPRODUCT_WEBHOOK_SECRET=<random>
autoproduct serve --port 8422
```

Point a GitHub webhook (pull_request events, JSON, the same secret) at
`/webhook/github`; POST incidents to `/incidents`. Workers run detached;
`GET /reviews` lists results. Multi-instance operation wants the Celery
supervisor from the design docs — not included yet.

## Crash recovery and checkpoint encryption

All three graphs — code review, deploy review, maintenance — checkpoint
every super-step to `.mas/checkpoints.db`. `autoproduct recover` (also
run automatically at `serve` startup) continues any run that has a
`meta.yaml` but no final mirror step from its last completed super-step;
a review paused at Gate 3 stays `awaiting_human`.

Set `AUTOPRODUCT_CHECKPOINT_KEY` (a raw passphrase or `secret://ENV_NAME`)
to encrypt checkpoint rows at rest (AES via pycryptodome). A key that
cannot be honored is a startup error, never a silent plaintext fallback;
each run's `meta.yaml` records `checkpoint_encryption: aes|off`. The YAML
mirrors stay plaintext on purpose — they are the human-readable audit
trail (doc 09 §6).

## Safety boundaries (structural, not configurable)

- No auto-merge, no production deploys, no L3/L4 tools for any voter.
- Fix-PRs and compound PRs are proposals; humans merge.
- Deep-mode test runs use the docker T3 sandbox when available; the
  `sandbox` field in every test report says which path ran. Subprocess
  fallback = trusted repos only.

## Key hygiene

Provider keys live in the environment only. If a key may have leaked,
rotate it at the provider console and update `~/.zshrc` (or your secret
store); nothing under `.mas/` or git should ever contain one.

## Quick-tunnel webhook (dogfood setup)

For laptop-grade operation: `cloudflared tunnel --url http://localhost:8422`
gives an ephemeral public URL; register it as the repo webhook (pull_request
events, JSON, the AUTOPRODUCT_WEBHOOK_SECRET value). The tunnel URL changes
on every restart — update the webhook config when it does.
