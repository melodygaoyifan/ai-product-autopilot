"""P3 launch & growth substrate (doc 21, weeks P3-P5) — safe-publish.

The seven deterministic backstops run before any voter and their union is
the P3 build gate; the autonomy ceiling means nothing in this package
publishes, sends, or spends — the checks prepare, a scoped human approval
at Gate PL3 releases. Voters, the experiment MAS, and the P0-P5 stage
rosters ship in later milestones.
"""

from ai_venture_studio.marketing.artifacts import (
    DomainAuth,
    Draft,
    EmailArtifact,
    Endorser,
    Page,
    Recipient,
)
from ai_venture_studio.marketing.brand_safety import (
    BrandConfig,
    BrandSafetyFinding,
    brand_and_safety_scan,
)
from ai_venture_studio.marketing.channels import (
    BUILTIN_CHANNELS,
    ChannelProfile,
    ChannelProfileError,
    load_channel_profiles,
)
from ai_venture_studio.marketing.deliverability import (
    DeliverabilityConfig,
    DeliverabilityConfigError,
    DeliverabilityFinding,
    deliverability_preflight,
    load_deliverability_config,
)
from ai_venture_studio.marketing.disclosure import (
    ComplianceProfile,
    ComplianceProfileError,
    DisclosureFinding,
    disclosure_lint,
    load_compliance_profile,
)
from ai_venture_studio.marketing.gate_pl3 import (
    ApprovalRecord,
    ApprovalScope,
    GateBlockedError,
    GatePL3Packet,
    artifact_hash,
    assemble_gate_packet,
    build_substantiation_map,
    record_approval,
)
from ai_venture_studio.marketing.geo_check import GeoFinding, geo_extractability_check
from ai_venture_studio.marketing.policy import (
    FORBIDDEN_AUTONOMOUS,
    AutonomyPolicyError,
    load_forbidden_autonomous,
)
from ai_venture_studio.marketing.register import (
    RegisteredClaim,
    ReleaseContract,
    ReleaseContractError,
    load_release_contract,
)
from ai_venture_studio.marketing.spam_policy import (
    SpamPolicyConfig,
    SpamPolicyFinding,
    spam_policy_check,
)
from ai_venture_studio.marketing.substantiation import (
    SubstantiationFinding,
    check_substantiation,
)
from ai_venture_studio.marketing.utm_lint import (
    TrackedAsset,
    UtmFinding,
    UtmTaxonomy,
    utm_and_instrumentation_lint,
)

__all__ = [
    "BUILTIN_CHANNELS",
    "FORBIDDEN_AUTONOMOUS",
    "ApprovalRecord",
    "ApprovalScope",
    "AutonomyPolicyError",
    "BrandConfig",
    "BrandSafetyFinding",
    "ChannelProfile",
    "ChannelProfileError",
    "ComplianceProfile",
    "ComplianceProfileError",
    "DeliverabilityConfig",
    "DeliverabilityConfigError",
    "DeliverabilityFinding",
    "DisclosureFinding",
    "DomainAuth",
    "Draft",
    "EmailArtifact",
    "Endorser",
    "GateBlockedError",
    "GatePL3Packet",
    "GeoFinding",
    "Page",
    "Recipient",
    "RegisteredClaim",
    "ReleaseContract",
    "ReleaseContractError",
    "SpamPolicyConfig",
    "SpamPolicyFinding",
    "SubstantiationFinding",
    "TrackedAsset",
    "UtmFinding",
    "UtmTaxonomy",
    "artifact_hash",
    "assemble_gate_packet",
    "brand_and_safety_scan",
    "build_substantiation_map",
    "check_substantiation",
    "deliverability_preflight",
    "disclosure_lint",
    "geo_extractability_check",
    "load_channel_profiles",
    "load_compliance_profile",
    "load_deliverability_config",
    "load_forbidden_autonomous",
    "load_release_contract",
    "record_approval",
    "spam_policy_check",
    "utm_and_instrumentation_lint",
]
