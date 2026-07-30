# autoproduct — operations runbook

Day-to-day operation of all four stages. Assumes `uv` and an
`ANTHROPIC_API_KEY` in the environment (other provider keys optional —
voters fall back visibly without them).

## Commands

| Command | What it does |
|---|---|
| `avs review <PR-URL \| git-range>` | Code Review + Test stages (Gates 1–3) |
| `avs resume <review-id> --decision ack\|override:<VERDICT>` | Continue a review paused at Gate 3 |
| `avs deploy-review <target>` | Gate 5 — deploy recommendation (never deploys) |
| `avs deploy-outcome <review-id> --outcome correct\|incorrect` | Record the human verdict; builds the trust-tier track record |
| `avs triage <incident-file> [--fix]` | Gate 6 — triage + root cause; `--fix` approves a fix-PR attempt |
| `avs replay [<review-id>]` | Audit trail of any past review |
| `avs bench` | Regression benchmark (bars: recall ≥40%, precision ≥50%) |
| `avs compound [--pr]` | Weekly signal aggregation → CLAUDE.md proposal |
| `avs serve` | Webhook mode (needs `AUTOPRODUCT_WEBHOOK_SECRET`) |
| `avs readiness` | Substrate-ladder report (docs 18–19): active stages at the declared rung, what each missing rung unlocks |
| `avs evidence-bundle <review-id>` | Export the Gate-R evidence bundle (unsigned v0) for CAB/change-control submission |
| `avs toolchain <language> [--manifest seeded.yaml]` | Run a language lane's det_tools slots (skipped = loud, never clean); with a seeded-defect manifest, measure catch-rate and register (or label PROVISIONAL) |
| `avs calibrate <language>` | Calibrate seeded-lane patterns against real scanners; per-defect report with actual slot output for each miss (run via `make calibrate`) |
| `avs eval-gate <scores.yaml> [--pin]` | Eval-set regression gate vs the pinned baseline; `--pin` re-baselines (commit the diff via PR) |
| `avs idempotency <run_a> <run_b>` | Backfill idempotency: the fixture-slice re-run must be byte-identical |
| `avs data-checks` | Run the workspace's external data checks (dbt auto-detected; others in `.mas/data-checks.yaml`) |
| `avs attest [<review-id>]` | Chain a review's gate/verdict records into the hash-chained attestation ledger, then verify the chain |
| `avs dwell` | Approval-dwell-time report (F-18.3): flags the rubber-stamp pattern (fast acks + zero overrides) |
| `avs cab-package <review-id>` | Assemble a CAB change package (evidence bundle + prefill) and run the Gate-R preflight; humans complete rollback/approver and submit |

## Substrate ladder (traditional-industry adoption, docs 18–19)

Opt-in: declare `.mas/substrate-profile.yaml` (schema in §18.47.1) and
stages below their infrastructure floor refuse with `STAGE_INACTIVE`
(exit code 4) instead of running vacuously — `deploy-review` degrades to
config-lint-only from S1 and says so. No profile file = no gating
(effective S4, unchanged behavior). Gate R rejections are recorded with
`ai_venture_studio.adoption.record_rejection` — mechanizable reasons become
preflight fixtures in `.mas/cab-preflight.yaml`, the rest land in
`.mas/cab-rejections.yaml` for the compounding loop. CAB submission
itself is human-only, always.

**Toolchain calibration (§19 G7).** The seeded-lane manifest patterns in
`tests/toolchains/seeded/{java,dotnet}/seeded.yaml` are hand-labels until a
real scanner run confirms them. `make calibrate` builds the
`Dockerfile.calibrate` image (Checkstyle, PIT, Semgrep, OWASP
Dependency-Check, Stryker, dotnet SDK) and runs `avs calibrate` per
lane, writing per-defect reports to `.mas/calibration/<lang>.yaml` and a
`calibration-summary.md` roll-up. A **miss on a slot that ran** means the
pattern is wrong — fix it in the manifest using the slot output the report
captured; a **skipped slot** means the scanner is absent. Re-run on every
scanner version bump (R-G3). `make calibrate-local` runs it on the host if
the scanners are already installed.

## Weekly rhythm

1. `avs compound --pr` — review and merge (or close) the proposal.
2. `avs bench` — must PASS; a regression after merging a compound
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
avs serve --port 8422
```

Point a GitHub webhook (pull_request events, JSON, the same secret) at
`/webhook/github`; POST incidents to `/incidents`. Workers run detached;
`GET /reviews` lists results. Multi-instance operation wants the Celery
supervisor from the design docs — not included yet.

## Crash recovery and checkpoint encryption

All three graphs — code review, deploy review, maintenance — checkpoint
every super-step to `.mas/checkpoints.db`. `avs recover` (also
run automatically at `serve` startup) continues any run that has a
`meta.yaml` but no final mirror step from its last completed super-step;
a review paused at Gate 3 stays `awaiting_human`.

Set `AUTOPRODUCT_CHECKPOINT_KEY` (a raw passphrase or `secret://ENV_NAME`)
to encrypt checkpoint rows at rest (AES via pycryptodome). A key that
cannot be honored is a startup error, never a silent plaintext fallback;
each run's `meta.yaml` records `checkpoint_encryption: aes|off`. The YAML
mirrors stay plaintext on purpose — they are the human-readable audit
trail (doc 09 §6).

## Releasing to PyPI

The distribution is `ai-venture-studio`; the commands it installs are `avs`
(documented) and `autoproduct` (alias, so older scripts keep working).

Publishing is done by CI through **Trusted Publishing** — there is no API
token in the repo, in a secret, or on anyone's laptop. A one-time setup at
<https://pypi.org/manage/account/publishing/> registers this repository and
`publish.yml` as the publisher; after that a release is:

```
# 1. bump the version and land it
#    pyproject.toml: version = "0.55.0"   (must match the CHANGELOG entry)
git commit -am "release: v0.55.0" && git push

# 2. tag it — this is what triggers the publish
git tag v0.55.0 && git push origin v0.55.0
```

The workflow runs the full suite on the tagged commit, checks the tag against
`pyproject.toml` (a mistyped tag fails instead of publishing a wrong number),
runs `twine check`, and only then uploads. The `pypi` environment can require
a manual approval if you want a human click before every release.

**A published version cannot be replaced, only yanked.** That is why the gate
is the whole suite rather than a smoke test, and why the version/tag check
exists.

One-off local publish (if you ever need it without CI): build, verify, then
upload with a token supplied by the environment — never pasted into a shell
that records history.

```
uv build && uvx twine check dist/*
UV_PUBLISH_TOKEN=pypi-... uv publish     # prefer: read it from a password manager
```

### The old distribution

`autoproduct` remains on PyPI at its last released version. PyPI has no
rename, so it stays there; `pip install autoproduct` keeps working and keeps
resolving to the old code. Two honest options, both deliberate rather than
accidental:

- **Leave it frozen** (current state) and point new users at the new name.
- **Publish one final `autoproduct` release** whose only change is a
  deprecation notice in the description pointing at `ai-venture-studio`.
  That requires temporarily setting `name = "autoproduct"` in a release
  branch, so it is a considered act, not a side effect.

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

## Enterprise environments (GitLab, Bedrock/Vertex, gateways)

**Forge.** Review targets can be GitHub PR URLs (github.com or GitHub
Enterprise Server, via `gh`) or GitLab MR URLs (gitlab.com or self-managed,
via `glab`) — `.../-/merge_requests/<n>` URLs dispatch to `glab`
automatically, subgroups included. Comments, HITL issues, fix-MRs, merges
(still policy-gated per ADR-031), and diff acquisition all follow the
target's forge; authenticate the matching CLI (`gh auth login` /
`glab auth login --hostname <your-host>`) first. Webhook mode (`avs serve`)
speaks GitHub pull_request events only today — on GitLab, run reviews from
CI or the CLI instead.

**Model door.** Direct API is the default. Two more doors, selected with
`AVS_ANTHROPIC_MODE`:

| Env | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | direct API (default) |
| `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` | enterprise LLM gateway / proxy, bearer auth |
| `AVS_ANTHROPIC_MODE=bedrock` | AWS Bedrock (`pip install 'anthropic[bedrock]'`, AWS credential chain) |
| `AVS_ANTHROPIC_MODE=vertex` + `ANTHROPIC_VERTEX_PROJECT_ID` + `CLOUD_ML_REGION` | GCP Vertex (`pip install 'anthropic[vertex]'`, ADC) |

Bedrock/Vertex use their own model IDs — put the platform's ID (e.g.
`anthropic.claude-*` on Bedrock) in your profile's model fields. Every
mode errors loudly on missing credentials; there is no silent fallback
between doors.

## Quick-tunnel webhook (dogfood setup)

For laptop-grade operation: `cloudflared tunnel --url http://localhost:8422`
gives an ephemeral public URL; register it as the repo webhook (pull_request
events, JSON, the AUTOPRODUCT_WEBHOOK_SECRET value). The tunnel URL changes
on every restart — update the webhook config when it does.
