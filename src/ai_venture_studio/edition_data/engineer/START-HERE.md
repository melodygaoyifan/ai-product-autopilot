# Engineer (SDE / MLE / agent engineer) — start here

You want a harness you can extend without inheriting a belief system by
accident. The one opinion you cannot opt out of: **deterministic checks
run before any LLM judgment, and nothing unfixtured registers.** The
ecosystem's median public skill scores 6.2/12 precisely because nothing
stops it from registering; here that is structural, and you are invited
to try to break it.

## Day 1

```bash
uvx avs replay --demo    # no API key: a real review's audit trail
avs bench                # one key: the seeded-defect catch rates, on your machine
avs init lab --profile web --edition engineer
```

## Extension points (each with a machine-checked contract)

| Extend | Contract | Where |
|---|---|---|
| Voter skills | YAML frontmatter + 8-fixture gate; ≥87.5% to register (`voter-gate`) | `skills/`, `tests/integration/voters/fixtures/` |
| Language lanes | seeded-defect manifest; **PROVISIONAL** until calibrated | design doc 19 |
| Domain/channel profiles | delta-only; a profile cannot weaken a core check | `profiles/`, `.mas/channel-profile.yaml` |
| Editions | `edition_lint` — narrowing-only, unknown keys refused | `editions/` |
| Deterministic tools | pure functions + fixture files; the suite is the gate | `src/ai_venture_studio/…`, `tests/` |

`avs bench` and `product-bench` are the regression bar your
modification must clear; `eval-gate` pins the baseline so a recall drop
shows in the diff.

## What you will not find, on purpose

No A2A/peer-messaging surface, no RL fine-tuning loop, no
orchestration-SDK shim — the harness *is* the orchestration opinion
(design doc 24 §71.2 records the revisit triggers honestly). MCP is the
transport bet; skill frontmatter deliberately tracks the Agent Skills
spec as a watch item, not a promise.

Read next: design doc 11 (the architectural keystone), then 08 → 09 for
the review pipeline you are standing on.
