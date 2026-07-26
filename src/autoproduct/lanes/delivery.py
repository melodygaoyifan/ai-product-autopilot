"""Delivery hardening (doc 28 Part 82): environments, flags, migrations.

environments.yaml is a promotion DAG ending at prod; perf baselines may
only cite prod_mirror runs. Flags are registered assets with owners and
expiry — removal is scheduled at creation because it is engineering work,
not a chore (ADR-U35, invariant 14.28). Migrations rehearse against a
fixture DB before review: applied cleanly, lock profile, and a
reversibility round-trip to a byte-identical schema dump.
"""

from __future__ import annotations

import datetime as dt
import re
import sqlite3

import yaml
from pydantic import BaseModel, Field

FLAG_CATEGORIES = ("release", "experiment", "migration", "ops_kill_switch",
                   "compat", "permission")
LONG_LIVED = ("ops_kill_switch", "permission")


class EnvironmentsError(RuntimeError):
    """Malformed promotion model. Fails closed."""


def check_environments(text: str) -> list[dict]:
    """The promotion graph is a DAG ending at prod; every named gate exists."""
    raw = yaml.safe_load(text) or {}
    envs = raw.get("environments") or []
    by_name = {str(e.get("name")): e for e in envs}
    if "prod" not in by_name:
        raise EnvironmentsError("no prod environment declared")
    for env in envs:
        target = env.get("promotes_to")
        if target is not None and target not in by_name:
            raise EnvironmentsError(
                f"{env.get('name')} promotes_to {target!r} which does not exist")
    # cycle/termination check: walk each env to prod
    for env in envs:
        seen, cursor = set(), env
        while cursor is not None:
            name = str(cursor.get("name"))
            if name in seen:
                raise EnvironmentsError(f"promotion cycle through {name!r}")
            seen.add(name)
            if name == "prod":
                break
            nxt = cursor.get("promotes_to")
            cursor = by_name.get(nxt) if nxt else None
        else:
            raise EnvironmentsError(
                f"{env.get('name')} has no promotion path ending at prod")
    return envs


def perf_run_environment_ok(envs: list[dict], environment: str, slot: str) -> bool:
    """perf_regression/perf_soak may only cite prod_mirror runs (§82.1)."""
    if slot not in ("perf_regression", "perf_soak"):
        return True
    env = next((e for e in envs if e.get("name") == environment), None)
    return bool(env and env.get("parity") == "prod_mirror")


class FlagIssue(BaseModel):
    flag: str
    rule: str
    message: str


_FLAG_REF = re.compile(r"flag\(\s*['\"]([\w.-]+)['\"]")


def flag_lint(
    registry_text: str, sources: dict[str, str], *, today: dt.date
) -> list[FlagIssue]:
    raw = yaml.safe_load(registry_text) or {}
    flags = {str(f.get("name")): f for f in raw.get("flags") or []}
    issues = []

    referenced = {m.group(1) for src in sources.values() for m in _FLAG_REF.finditer(src)}
    for name in sorted(referenced - set(flags)):
        issues.append(FlagIssue(
            flag=name, rule="unregistered_flag",
            message="referenced in code but absent from .mas/flags.yaml — "
                    "unregistered quick flags are the stale flags of six "
                    "months from now (ADR-U35)"))

    for name, flag in sorted(flags.items()):
        category = flag.get("category")
        if category not in FLAG_CATEGORIES:
            issues.append(FlagIssue(flag=name, rule="bad_category",
                                    message=f"category must be one of {FLAG_CATEGORIES}"))
            continue
        for field in ("owner", "created", "final_state", "removal_trigger"):
            if not flag.get(field):
                issues.append(FlagIssue(
                    flag=name, rule="incomplete_registration",
                    message=f"missing {field!r} — removal is scheduled at "
                            "creation time, not discovered later"))
        expiry = flag.get("expiry")
        if category not in LONG_LIVED:
            if not expiry:
                issues.append(FlagIssue(
                    flag=name, rule="no_expiry",
                    message=f"category {category!r} flags must expire — only "
                            f"{LONG_LIVED} may be long-lived"))
            else:
                expiry_date = dt.date.fromisoformat(str(expiry))
                if today > expiry_date + dt.timedelta(days=7):
                    issues.append(FlagIssue(
                        flag=name, rule="expired_blocking",
                        message=f"expired {expiry} and the grace week has "
                                "passed — Gate 2 blocks until removed"))
                elif today > expiry_date:
                    issues.append(FlagIssue(
                        flag=name, rule="expired_grace",
                        message=f"past expiry {expiry}; grace week running"))
    return issues


class RehearsalRecord(BaseModel):
    status: str  # VALID | INVALID_REHEARSAL
    applied_cleanly: bool = False
    reversible: bool = False
    destructive_ops: list[str] = Field(default_factory=list)
    detail: str = ""


_DESTRUCTIVE = re.compile(r"\b(DROP\s+TABLE|DROP\s+COLUMN|ALTER\s+TABLE\s+\w+\s+DROP)\b", re.I)


def _schema_dump(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
    ).fetchall()
    return "\n".join(f"{t}|{n}|{s}" for t, n, s in rows)


def migration_rehearsal(
    fixture_schema_sql: str, up_sql: str, down_sql: str
) -> RehearsalRecord:
    """Run the migration against a fixture DB (S0 tier: in-memory SQLite);
    reversibility = the down-migration round-trips to a byte-identical
    schema dump. A destructive change without this record never reaches
    review (invariant 14.28)."""
    destructive = [m.group(0) for m in _DESTRUCTIVE.finditer(up_sql)]
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(fixture_schema_sql)
        before = _schema_dump(conn)
        try:
            conn.executescript(up_sql)
        except sqlite3.Error as exc:
            return RehearsalRecord(status="INVALID_REHEARSAL",
                                   destructive_ops=destructive,
                                   detail=f"up-migration failed: {exc}")
        try:
            conn.executescript(down_sql)
        except sqlite3.Error as exc:
            return RehearsalRecord(status="VALID", applied_cleanly=True,
                                   reversible=False, destructive_ops=destructive,
                                   detail=f"down-migration failed: {exc}")
        after = _schema_dump(conn)
        reversible = before == after
        return RehearsalRecord(
            status="VALID", applied_cleanly=True, reversible=reversible,
            destructive_ops=destructive,
            detail="round-trips to a byte-identical schema dump" if reversible
            else "down-migration does not restore the schema — irreversible "
                 "on the record")
    finally:
        conn.close()


def expand_contract_violation(up_sql: str, *, same_pr_as_expand: bool) -> bool:
    """Expand-migrate-contract: contract steps land in separate, later PRs
    by construction (§82.3)."""
    return bool(_DESTRUCTIVE.search(up_sql)) and same_pr_as_expand
