"""The JS gate must not run preserved failures as if they were the product.

`.mas/failed-builds/<slug>/` holds copies of FAILED attempts, and pathlib's
`**` walks hidden directories — so once one task failed, every later task's
build gate ran that task's broken snapshot. In one real workspace the glob
matched 37 files, 31 of them inside `.mas`.
"""
from __future__ import annotations

import shutil

import pytest

from ai_venture_studio.testing import run_js_tests

PASSING = """const { test } = require('node:test')
test('ok', () => {})
"""
FAILING = """const { test } = require('node:test')
const assert = require('node:assert')
test('broken', () => { assert.strictEqual(1, 2) })
"""


@pytest.fixture
def product(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "ok.test.js").write_text(PASSING, encoding="utf-8")
    return tmp_path


pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not on PATH"
)


def test_a_preserved_failure_does_not_fail_the_next_task(product):
    snapshot = product / ".mas" / "failed-builds" / "earlier-task" / "tests"
    snapshot.mkdir(parents=True)
    (snapshot / "broken.test.js").write_text(FAILING, encoding="utf-8")

    report = run_js_tests(product)

    assert report.status == "passed", (
        "a preserved failed attempt was run as if it were the product"
    )


def test_the_products_own_failing_test_still_fails(product):
    (product / "tests" / "bad.test.js").write_text(FAILING, encoding="utf-8")
    assert run_js_tests(product).status == "failed"


@pytest.mark.parametrize("skipped", ["node_modules", ".git", ".venv"])
def test_vendored_and_scm_directories_are_skipped(product, skipped):
    d = product / skipped / "pkg"
    d.mkdir(parents=True)
    (d / "vendor.test.js").write_text(FAILING, encoding="utf-8")
    assert run_js_tests(product).status == "passed"
