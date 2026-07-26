---
metric:
  id: weekly_maintenance_attention_hours
  definition: "human hours spent per week on framework maintenance: gate reviews, incident triage, dependency/doc upkeep — logged, not estimated"
  numerator_event: maintenance.attention_logged
  denominator: "one calendar week"
  window_days: 7
  cohort_basis: calendar_week
  exclusions: ["feature development by choice", "usage of the framework on product work"]
  owner: human
  changed_at: ""
---

# weekly_maintenance_attention_hours

The metric by which the platform's own launch is falsifiable (doc 25
§76.4, pointing §22.66.4 at ourselves): if maintaining the framework costs
more attention than it frees, the honest response is cutting scope at Gate
PL5 — the launch PRD's kill criterion says exactly that. Human-owned;
logged hours only (an estimate of one's own attention is the least
trustworthy number in this repo).
