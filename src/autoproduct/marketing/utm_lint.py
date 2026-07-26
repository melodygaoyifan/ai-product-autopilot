"""utm_and_instrumentation_lint (§21.58.7) — boring, and why P4 has data.

UTM grammar against a fixed taxonomy; no PII in URL parameters ever (the
standing privacy rule, shared with user_data_taint §22.64); every asset's
conversion event exists in the analytics schema before publish; every
experiment arm carries its assignment parameter. A campaign that ships
without instrumentation cannot be evaluated, and an outer loop that cannot
evaluate is not a loop.
"""

from __future__ import annotations

import re
import urllib.parse

from pydantic import BaseModel, Field

_PII_VALUE = re.compile(
    r"[\w.+-]+@[\w-]+\.[\w.]+|"  # email
    r"(?:\+?\d{1,3}[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}"  # phone
)
_REQUIRED_UTM = ("utm_source", "utm_medium", "utm_campaign")


class UtmTaxonomy(BaseModel):
    sources: list[str] = Field(default_factory=list)
    mediums: list[str] = Field(default_factory=list)


class TrackedAsset(BaseModel):
    id: str
    url: str
    conversion_event: str = ""
    experiment_id: str = ""  # non-empty means this asset is an experiment arm


class UtmFinding(BaseModel):
    rule: str
    asset_id: str
    message: str


def utm_and_instrumentation_lint(
    assets: list[TrackedAsset],
    *,
    taxonomy: UtmTaxonomy | None = None,
    analytics_events: set[str] = frozenset(),
    assignment_param: str = "exp_arm",
) -> list[UtmFinding]:
    taxonomy = taxonomy or UtmTaxonomy()
    findings = []
    for asset in assets:
        params = dict(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(asset.url).query)
        )

        for required in _REQUIRED_UTM:
            if not params.get(required):
                findings.append(
                    UtmFinding(
                        rule="utm_grammar",
                        asset_id=asset.id,
                        message=f"missing {required}",
                    )
                )
        if taxonomy.sources and params.get("utm_source") not in [
            *taxonomy.sources,
            None,
        ]:
            findings.append(
                UtmFinding(
                    rule="utm_taxonomy",
                    asset_id=asset.id,
                    message=f"utm_source {params.get('utm_source')!r} not in the "
                    "fixed taxonomy",
                )
            )
        if taxonomy.mediums and params.get("utm_medium") not in [
            *taxonomy.mediums,
            None,
        ]:
            findings.append(
                UtmFinding(
                    rule="utm_taxonomy",
                    asset_id=asset.id,
                    message=f"utm_medium {params.get('utm_medium')!r} not in the "
                    "fixed taxonomy",
                )
            )

        for key, value in params.items():
            if _PII_VALUE.search(urllib.parse.unquote(value)):
                findings.append(
                    UtmFinding(
                        rule="pii_in_url",
                        asset_id=asset.id,
                        message=f"parameter {key!r} carries PII — never, in any "
                        "URL (§22.64 standing rule)",
                    )
                )

        if not asset.conversion_event:
            findings.append(
                UtmFinding(
                    rule="missing_conversion_event",
                    asset_id=asset.id,
                    message="asset declares no conversion event",
                )
            )
        elif asset.conversion_event not in analytics_events:
            findings.append(
                UtmFinding(
                    rule="unknown_conversion_event",
                    asset_id=asset.id,
                    message=f"conversion event {asset.conversion_event!r} does not "
                    "exist in the analytics schema — instrument before publish",
                )
            )

        if asset.experiment_id and assignment_param not in params:
            findings.append(
                UtmFinding(
                    rule="missing_assignment_param",
                    asset_id=asset.id,
                    message=f"experiment arm lacks its {assignment_param!r} "
                    "assignment parameter",
                )
            )
    return findings
