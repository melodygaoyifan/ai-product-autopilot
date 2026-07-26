"""External data-stack wrappers (§18.48.1's dbt/GE path; §19 G10-G12).

Data stacks vary too much for a builtin slot table, so checks are
discovered (dbt detected by dbt_project.yml) and declared
(`.mas/data-checks.yaml`: `checks: {name: argv}`). Execution reuses the
toolchain slot runner: availability-gated, a missing binary is `skipped`
and skipped is never clean. A workspace with no checks at all gets an
explicit `unconfigured` result rather than an empty (clean-looking) report.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from autoproduct.adoption.toolchains import SlotResult, run_slot

DATA_CHECKS_CONFIG = ".mas/data-checks.yaml"


def data_check_spec(repo_dir: str | Path) -> dict[str, list[str]]:
    root = Path(repo_dir)
    spec: dict[str, list[str]] = {}
    if (root / "dbt_project.yml").exists():
        spec["dbt_compile"] = ["dbt", "compile"]
        spec["dbt_test"] = ["dbt", "test"]
    config = root / DATA_CHECKS_CONFIG
    if config.exists():
        data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
        for name, argv in (data.get("checks") or {}).items():
            if not isinstance(argv, list) or not argv:
                raise ValueError(
                    f"{config}: checks.{name} must be a non-empty argv list"
                )
            spec[str(name)] = [str(a) for a in argv]
    return spec


def run_data_checks(repo_dir: str | Path) -> list[SlotResult]:
    spec = data_check_spec(repo_dir)
    if not spec:
        return [SlotResult(
            slot="data_checks", status="skipped",
            detail=(
                "no dbt project detected and no .mas/data-checks.yaml — "
                "NOT checked, not clean"
            ),
        )]
    return [run_slot(repo_dir, name, argv) for name, argv in spec.items()]
