"""A 小程序 cannot run Python, and prose could not enforce it (item P1.3).

The mini-program stack_hint says "a .py test file in a 小程序 project is
always wrong". A spec came back with `tests/test_catalog_page.py` anyway,
which made the build gate demand a passing pytest run against a project
with no Python in it; the task died three iterations later on "pytest
collected no tests" — a true sentence about the wrong thing.

Two boundaries, because the mistake has two chances to happen: the spec
that asks for the file, and the write that would create it.
"""

import shutil

import pytest

from ai_venture_studio.upstream.build import _write_files, foreign_language_issue
from ai_venture_studio.upstream.spec import _foreign_skeletons

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)


def test_python_is_foreign_to_a_miniprogram():
    issue = foreign_language_issue("miniprogram", "tests/test_catalog_page.py")
    assert issue and "cannot run" in issue
    assert "*.test.js" in issue, "a refusal must name the right way to do it"


def test_javascript_and_wxml_are_native_to_a_miniprogram():
    for path in ("miniprogram/utils/cart.test.js", "miniprogram/pages/x/x.wxml",
                 "miniprogram/app.json"):
        assert foreign_language_issue("miniprogram", path) is None


def test_python_is_fine_in_a_web_product():
    """The rule is per-runtime, not a dislike of Python: the web profile IS
    Python (stdlib http.server or FastAPI)."""
    assert foreign_language_issue("web", "tests/test_orders.py") is None


def test_an_unknown_or_absent_profile_restricts_nothing():
    assert foreign_language_issue("", "tests/test_x.py") is None
    assert foreign_language_issue("game", "tests/test_x.py") is None


def test_the_spec_blocks_a_skeleton_in_the_wrong_language():
    spec_data = {
        "criteria": ["When a user taps add, the cart shall show the item."],
        "test_skeletons": [
            {"path": "tests/test_catalog_page.py", "purpose": "p", "covers": [0]},
        ],
    }
    issues = _foreign_skeletons(spec_data, "miniprogram")
    assert len(issues) == 1
    assert "test_catalog_page.py" in issues[0]

    ok = {"test_skeletons": [
        {"path": "miniprogram/utils/cart.test.js", "purpose": "p", "covers": [0]}
    ]}
    assert _foreign_skeletons(ok, "miniprogram") == []


def test_the_write_boundary_refuses_the_file_itself(tmp_path):
    """Even if a spec slipped through, the file never lands — and the
    refusal is feedback the build loop can retry against, not a crash."""
    from ai_venture_studio.upstream import init_workspace

    root = init_workspace(tmp_path / "mp", "mp", "miniprogram")

    with pytest.raises(ValueError) as exc:
        _write_files(root, [
            {"path": "miniprogram/utils/cart.js", "new_content": "module.exports={}\n"},
            {"path": "tests/test_cart.py", "new_content": "def test_x(): pass\n"},
        ])

    assert "wrong language" in str(exc.value)
    # Two-pass validation: the legitimate file was NOT written either, so a
    # refused batch leaves no partial state behind.
    assert not (root / "miniprogram" / "utils" / "cart.js").exists()
    assert not (root / "tests" / "test_cart.py").exists()


def test_a_web_workspace_still_takes_python(tmp_path):
    from ai_venture_studio.upstream import init_workspace

    root = init_workspace(tmp_path / "w", "w", "web")
    written, _kept = _write_files(
        root, [{"path": "tests/test_orders.py", "new_content": "def test_x(): pass\n"}]
    )
    assert written == ["tests/test_orders.py"]
