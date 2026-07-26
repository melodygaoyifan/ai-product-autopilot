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
- **Starter set, not the target set.** ~10 planted defects per lane here;
  doc 19 G7 calls for ~30 sourced from the pilot's real historical bugs.
  Expansion rides the pilot (logged so this never reads as "covered").

Hermetic CI validates manifest structure and that every planted file
exists; running the real scanners is availability-gated and manual.
