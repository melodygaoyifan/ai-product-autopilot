---
metric:
  id: activation_rate
  definition: "share of new workspaces that complete first export within 7 days of creation"
  numerator_event: workspace.first_export
  denominator: "workspaces created in cohort window"
  window_days: 7
  cohort_basis: signup_week
  exclusions: ["internal domains", "test workspaces"]
  owner: human
  changed_at: ""
---

# activation_rate

The activation moment for avs is the **first successful export**:
it is the earliest event that proves a founder got real value out (the
product built something and they took it away). Chosen over first-build
because builds can succeed while the founder never returns for the result.

Human-owned (§22.62.3). Changing this definition is a breaking change:
record `changed_at`, reset the baseline, keep the old series labeled —
comparing across the change is a Metric-Definition voter finding (F-22.1).
