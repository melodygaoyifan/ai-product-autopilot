# Solo / OPC (一人公司) — start here

You are one person. The build barrier collapsed; the distribution barrier
did not. This edition is built around your one scarce resource — attention
— and its differentiator is not the coding pipeline (everyone sells you a
build tool): it is the claim ledger, the marketing backstops, the
experiment machinery, and the kill discipline (design docs 20–23).

## Day 1

```bash
uvx autoproduct replay --demo        # no API key: see a real audit trail (3 min)
autoproduct init mycompany --profile web --edition solo
cd mycompany && autoproduct studio   # describe your product in your own words
```

Then run Day-0 calibration (design repo `day-0-calibration.md`) before
trusting any time estimate — including ours.

## Your operating rhythm

- **One product bet at a time** (`wip_limit: 1` — the preset, not advice).
- **One weekly review, 30–45 minutes** — the agenda is
  [weekly-review.md](weekly-review.md), in priority order; fired kill
  criteria come first and cannot be batched (they interrupt the week).
- **Publishing defaults to `content_geo` + `product_surface`** — email
  needs deliverability telemetry a fresh domain doesn't have (§21.58.3).
  Raising any preset is one line in `.mas/edition.yaml`; the lint only
  stops you from *widening* past framework floors.

## What to read when you need it

- Deciding what to build → design doc 20 (the claim ledger first, §53).
- Before anything publishes → doc 21 §58 (the seven backstops run anyway).
- When a kill criterion fires → doc 22 §65. The registry remembers so you
  don't have to re-argue with yourself in six months.

Everything you batch still writes its full gate record — your ledger is
identical to an enterprise's (invariant 14.22). That log is what makes a
later fundraise or acquisition diligence survivable.
