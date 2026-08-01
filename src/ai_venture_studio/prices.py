"""Reference prices — what makes the cost gate able to fire.

`cost_gate` has been complete since v0.59.0 and inert ever since, because
`CostModel.prices` defaults to empty: every call was UNPRICED, the month's
total was reported as a floor, and a cap compared against a floor never
bites. The mechanism was right and the table was missing.

This module ships a table of **published list prices** with a source URL and
a retrieval date (`prices.yaml`), and imports it into a workspace's
`.mas/cost-model.yaml` on request. Three rules keep it honest:

1. **Nothing is invented.** Every entry cites the vendor page it came from
   and the date it was read — the evidence standard `claim_lint` applies to
   every other number here.
2. **Ranges resolve upward.** A cap exists to stop spend, so under-counting
   is the failure mode that matters; a tiered or introductory price is
   recorded at its most expensive form, with the reason on the entry. The
   estimate is a ceiling.
3. **Prices rot, and the table says so.** `retrieved_at` plus
   `stale_after_days` means an old table announces itself instead of quietly
   costing a month at last quarter's rates.

They are list prices, not *your* prices — enterprise agreements, credits,
Bedrock/Vertex rates and batch discounts all differ. Import writes them into
the workspace, where they are yours to correct.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import yaml
from pydantic import BaseModel, Field

from ai_venture_studio.paths import package_root

PRICES_FILE = "prices.yaml"
COST_MODEL_FILE = "cost-model.yaml"


class PriceEntry(BaseModel):
    model: str
    provider: str
    input: float = Field(ge=0)
    output: float = Field(ge=0)
    note: str = ""


class ReferencePrices(BaseModel):
    retrieved_at: str
    stale_after_days: int = 90
    sources: dict[str, str] = Field(default_factory=dict)
    entries: list[PriceEntry] = Field(default_factory=list)

    def age_days(self, today: dt.date | None = None) -> int:
        today = today or dt.date.today()
        return (today - dt.date.fromisoformat(self.retrieved_at)).days

    def stale(self, today: dt.date | None = None) -> bool:
        return self.age_days(today) > self.stale_after_days

    def as_cost_model_prices(self) -> dict[str, dict[str, float]]:
        return {e.model: {"input": e.input, "output": e.output} for e in self.entries}


def reference_path() -> pathlib.Path:
    return package_root() / PRICES_FILE


def load_reference_prices(path: str | pathlib.Path | None = None) -> ReferencePrices:
    raw = yaml.safe_load(
        pathlib.Path(path or reference_path()).read_text(encoding="utf-8")
    ) or {}
    return ReferencePrices(
        retrieved_at=str(raw.get("retrieved_at", "")),
        stale_after_days=int(raw.get("stale_after_days", 90)),
        sources=dict(raw.get("sources") or {}),
        entries=[
            PriceEntry(model=name, **{k: v for k, v in (body or {}).items()})
            for name, body in sorted((raw.get("prices") or {}).items())
        ],
    )


class ImportResult(BaseModel):
    path: str
    models_written: list[str] = Field(default_factory=list)
    models_kept: list[str] = Field(default_factory=list)
    cap_usd: float = 0.0
    stale: bool = False
    age_days: int = 0


def import_into_workspace(
    repo_dir: str | pathlib.Path,
    *,
    cap_usd: float | None = None,
    overwrite: bool = False,
    reference: ReferencePrices | None = None,
    today: dt.date | None = None,
) -> ImportResult:
    """Write the reference prices into `.mas/cost-model.yaml`.

    A price already in the workspace WINS by default: the operator's own
    number — a negotiated rate, a correction — must not be silently replaced
    by a list price on the next import. `overwrite=True` is the explicit way
    to refresh them. An existing `monthly_cap_usd` is preserved unless a new
    cap is passed, because importing prices is not the same act as changing
    the budget.
    """
    prices = reference or load_reference_prices()
    mas = pathlib.Path(repo_dir).resolve() / ".mas"
    mas.mkdir(parents=True, exist_ok=True)
    path = mas / COST_MODEL_FILE

    existing: dict = {}
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    current: dict = dict(existing.get("prices") or {})

    written, kept = [], []
    for model, price in prices.as_cost_model_prices().items():
        if model in current and not overwrite:
            kept.append(model)
            continue
        current[model] = price
        written.append(model)

    cap = float(existing.get("monthly_cap_usd", 0.0) or 0.0)
    if cap_usd is not None:
        cap = float(cap_usd)

    path.write_text(
        "# Written by `avs prices --import`. These are LIST prices with a\n"
        f"# source and a date ({prices.retrieved_at}); they are not necessarily\n"
        "# yours. Correct any of them — a price already here is never\n"
        "# overwritten by a later import unless you pass --overwrite.\n"
        "# monthly_cap_usd: 0 means no cap is configured (stated, not silent).\n"
        + yaml.safe_dump(
            {"prices": current, "monthly_cap_usd": cap},
            sort_keys=True, allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return ImportResult(
        path=str(path), models_written=sorted(written), models_kept=sorted(kept),
        cap_usd=cap, stale=prices.stale(today), age_days=prices.age_days(today),
    )


def unpriced_models(
    repo_dir: str | pathlib.Path, *, month: str | None = None
) -> list[str]:
    """Models this workspace actually called that no price covers.

    The honest complement to a price table: it names what the total is still
    a floor over, rather than leaving the gap as a count.
    """
    from ai_venture_studio.observability import load_cost_model
    from ai_venture_studio.spend import current_month, read_entries

    root = pathlib.Path(repo_dir).resolve()
    model = load_cost_model(root / ".mas")
    seen = {e.model for e in read_entries(root, month=month or current_month())}
    return sorted(m for m in seen if m not in model.prices)
