# ADR-031 — Merge and deploy execution, armed by human policy only

- **Status:** accepted, v0.39.0
- **Reverses:** "Auto-merge to main. Auto-deploy to production. Auto-hotfix."
  as out-of-scope (README), and softens the §08.1.8 "hard architectural
  ceiling" phrasing to a **policy-armed** ceiling
- **Does not reverse:** auto-hotfix, or any path where an agent decides
  that automation is acceptable

## Context

The prior ceiling was structural: no merge or deploy code path existed at
all. That was the right default and it is still the default. But "the code
cannot do it" and "the system decides on its own" are different claims,
and only the second one was ever the real safety property.

A team that has watched fifty reviews land correct verdicts, on a repo
where CI is trustworthy and branch protection is configured, is making a
reasonable engineering decision when they say "squash-merge APPROVE
verdicts on `main` for the next 90 days." Refusing that forever is not
safety; it is the framework substituting its judgment for theirs about
their own repository.

The genuine risk is not delegation. It is **an agent talking itself into a
merge** — a voter that finds nothing because it was blocked, a leader that
softens a verdict, a policy that quietly stays armed after the conditions
that justified it stopped holding.

## Decision

Ship both capabilities, disarmed, behind a human-authored policy file per
repository:

- `.mas/automerge-policy.yaml` → `avs automerge <review-id>`
- `.mas/deploy-exec-policy.yaml` → `avs deploy-execute <id>`

The system never decides *whether* automation is acceptable. A human does,
in advance, in writing, in a file they own. The system's job is to refuse
unless every declared condition mechanically holds.

## Mechanism (what keeps it bounded)

1. **Disarmed by default, and absence is never permission.** No file → no
   automation. A present file defaults to `enabled: false`. There is no
   flag, env var, or prompt that arms automation without that file.
2. **Narrow by construction.** `branches:` holds exact strings; `"*"` and
   any glob character is a `PolicyError`. A policy cannot arm what it does
   not name.
3. **Attributed and expiring.** `armed_by:` (who decided) and
   `expires_at:` (when the decision lapses) are both required. An expired
   policy is a hard error, never a silent continuation — standing
   permission that never lapses is how this stops being a decision.
4. **Earned.** `min_track_record` correct recommendations, read from the
   same `.mas/deploy-track-record.yaml` the deploy trust tiers use, must
   exist before the first automated action. The first automated action is
   never the first action.
5. **Verdict class is a whitelist.** Only `APPROVE` and
   `APPROVE_WITH_NOTES` may precede a merge; every `ESCALATE_*`,
   `REQUEST_CHANGES`, and anything unrecognized is excluded by omission.
   An escalated review's decision stands even if the verdict was later
   overridden to an approve class.
6. **Paths that always demand a human**, whatever the policy says:
   migrations, Terraform, Dockerfiles, CI workflows, Helm/k8s manifests,
   `CLAUDE.md`, anything under `.mas/`, and **the policy files themselves**
   — automation may never widen its own permissions.
7. **The system never composes a deploy command.** `deploy-execute` runs
   the exact argv in `command:`, with no shell, or it refuses. A policy
   with no command is refused even when otherwise armed.
8. **No `--admin` escape.** Merges go through `gh pr merge` without
   `--admin`: if branch protection blocks it, that is a human's configured
   intent and the merge must fail rather than override it.
9. **Both directions are logged.** `.mas/automation-log.jsonl` records
   actions *and* refusals with their exact reasons, because "why didn't it
   merge" deserves the same answer quality as "why did it".

## What stays out

- **Auto-hotfix** — unchanged, still out. A production incident is the
  worst moment to discover a policy was too broad.
- **Any agent-side arming.** No voter, leader, sweep, or compounding PR may
  create or edit a policy file; they are on the always-human path list, so
  a diff touching them cannot itself be auto-merged.
- **Auto-approval of its own PRs.** The compounding loop and Sweep still
  open PRs that a human merges; nothing here changes who approves them.

## Consequences

- Teams can delegate the mechanical part of merging without the framework
  pretending the delegation did not happen.
- The invariant in `CLAUDE.md` changes from "the system never merges" to
  "the system never merges unless a human armed a policy that says exactly
  when" — a weaker claim, honestly stated, with a mechanism behind it.
- The audit question shifts from "could it have merged?" to "which policy
  allowed this, who armed it, and when does it expire?" — all three
  answerable from the repository.
