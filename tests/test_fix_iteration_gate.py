"""A fix iteration must clear the same bar as the build gate.

`fix: address serious review findings` deleted an `onAdd` handler from a
committed page. cart.page.test.js started failing. Because the build gate
runs the WHOLE suite and existing tests are read-only walls to later
implementers, the next four tasks could not be built — one unchecked fix
cost four modules.

It was unchecked because the fix iteration ran bare pytest, which returns
"no_tests" on a 小程序, while the build loop runs
combine_reports(pytest, js). Two standards in one repo.
"""
from __future__ import annotations

import inspect

# aliased: pytest tries to collect any imported name starting with Test
from ai_venture_studio.testing import TestReport as _Report
from ai_venture_studio.testing import combine_reports
from ai_venture_studio.upstream import autopilot


def test_the_fix_iteration_runs_the_javascript_suite_too():
    source = inspect.getsource(autopilot._fix_iteration)
    assert "run_js_tests" in source, "a JS product's fix would go unchecked"
    assert "combine_reports" in source
    assert "_pytest_in_subprocess(root).status not in" not in source, (
        "the bare-pytest check is what let the broken fix through"
    )


def test_a_failing_js_suite_blocks_even_when_pytest_is_empty():
    """The exact shape of the miss: no Python, failing JavaScript."""
    verdict = combine_reports(
        _Report(status="no_tests", summary="pytest collected no tests"),
        _Report(status="failed", summary="2 failing"),
    )
    assert verdict.status == "failed"
    assert verdict.status not in ("passed", "no_tests", "skipped")


def test_a_product_with_no_tests_at_all_still_passes():
    """The guard must not block a task that legitimately has no suite."""
    verdict = combine_reports(
        _Report(status="no_tests", summary="none"), None
    )
    assert verdict.status in ("passed", "no_tests", "skipped")


def test_a_visible_skip_is_not_a_failure():
    """node missing is a visible skip, not a reason to revert a good fix."""
    verdict = combine_reports(
        _Report(status="no_tests", summary="none"),
        _Report(status="skipped", summary="node is not installed"),
    )
    assert verdict.status in ("passed", "no_tests", "skipped")
