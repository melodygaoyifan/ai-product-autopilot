"""P4 product-evidence substrate (doc 22, weeks P6-P8) — honest measurement.

Stage 8 sees a healthy system; P4 sees a product with 100% uptime and 4%
activation. This package is the deterministic layer: the privacy boundary
(person-level data never leaves — enforced as errors, not instructions),
the metric vocabulary, cohort readings with teeth, attribution typed at
the tool boundary, and holdouts as the only path to a causal claim. The
P4 voter roster and Leader ride the standing MAS machinery; their skills
live in skills/product/evidence/.
"""

from autoproduct.evidence.analytics import (
    PERSON_LEVEL_FIELDS,
    AnalyticsStore,
    CohortAggregate,
    CohortTooSmallError,
    PersonLevelQueryError,
    pii_scan,
)
from autoproduct.evidence.attribution import (
    ATTRIBUTION_RULES,
    AttributionFinding,
    AttributionMethodError,
    TypedObservation,
    attribute_claim,
    type_observation,
)
from autoproduct.evidence.cohort import (
    CohortReading,
    SufficiencyVerdict,
    cohort_calc,
    sample_sufficiency_check,
    wilson_interval,
)
from autoproduct.evidence.feedback import FeedbackArtifact, FeedbackStore
from autoproduct.evidence.gate_pl4 import (
    GatePL4Result,
    OutcomeReason,
    gate_pl4,
)
from autoproduct.evidence.holdout import (
    ExposureLog,
    HoldoutAssignment,
    HoldoutComparison,
    assign_geo_holdout,
    assign_holdout,
    compare_holdout,
)
from autoproduct.evidence.metrics import (
    MetricDefinition,
    MetricIssue,
    MetricVocabularyError,
    baseline_comparable,
    comparison_issues,
    load_metric_vocabulary,
    metric_definition_check,
)
from autoproduct.evidence.signal_router import (
    AMBIGUOUS_CLASSES,
    P4_CLASSES,
    STAGE8_CLASSES,
    Routing,
    Signal,
    route_signal,
)

__all__ = [
    "AMBIGUOUS_CLASSES",
    "ATTRIBUTION_RULES",
    "PERSON_LEVEL_FIELDS",
    "P4_CLASSES",
    "STAGE8_CLASSES",
    "AnalyticsStore",
    "AttributionFinding",
    "AttributionMethodError",
    "CohortAggregate",
    "CohortReading",
    "CohortTooSmallError",
    "ExposureLog",
    "FeedbackArtifact",
    "FeedbackStore",
    "GatePL4Result",
    "HoldoutAssignment",
    "HoldoutComparison",
    "MetricDefinition",
    "MetricIssue",
    "MetricVocabularyError",
    "OutcomeReason",
    "PersonLevelQueryError",
    "Routing",
    "Signal",
    "SufficiencyVerdict",
    "TypedObservation",
    "assign_geo_holdout",
    "assign_holdout",
    "attribute_claim",
    "baseline_comparable",
    "cohort_calc",
    "compare_holdout",
    "comparison_issues",
    "gate_pl4",
    "load_metric_vocabulary",
    "metric_definition_check",
    "pii_scan",
    "route_signal",
    "sample_sufficiency_check",
    "type_observation",
    "wilson_interval",
]
