# Seeded reference repos (§19 G7)

One mini-repo per language lane, with hand-planted defects and a
`seeded.yaml` manifest mapping each defect to the det_tools slot that must
catch it. This is the fixture gate for toolchains (ADR-U16): a language
registers first-class only after `autoproduct toolchain <lang>
--manifest tests/toolchains/seeded/<lang>/seeded.yaml` measures its
catch-rate here.

Two calibration notes, per the doc-19 G7 discipline:

- **Patterns are the hand-labeling.** Each manifest `pattern` is the
  substring expected in the catching slot's output. Scanner output formats
  vary by version — the first real (non-hermetic) run against installed
  scanners calibrates them, and every toolchain version bump re-runs the
  benchmark (risk R-G3).
- **Toward the target set.** ~20 planted defects per lane now (App.* +
  Payments.*), spanning the full slot range; doc 19 G7 calls for ~30
  sourced from the pilot's real historical bugs. The remaining ~10 ride the
  pilot (logged so this never reads as "covered") — synthetic defects prove
  the harness measures, real defects prove it measures what matters.

Hermetic CI validates manifest structure and that every planted file
exists; running the real scanners is availability-gated and manual.

**Calibrating the patterns.** `make calibrate` (from the repo root) builds
the scanner container and runs `autoproduct calibrate` per lane, producing
`.mas/calibration/<lang>.yaml` — for every planted defect, caught or missed,
and the actual scanner output for each miss. When a pattern here misses a
defect the scanner *did* flag, copy the right substring out of that captured
output into this manifest's `pattern`. That is the whole calibration loop.
