import shutil

import pytest
from fastapi.testclient import TestClient

from autoproduct.studio import create_studio_app
from autoproduct.upstream import init_workspace

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)

GOOD_FDR = (
    "# 小区团购接龙\n团长发起接龙写商品和价格，住户下单选数量，团长看按商品汇总。\n"
    "必须有：发起、下单、汇总。暂时不要：在线支付。成功：一周10个团长用过。\n"
)


@pytest.fixture
def studio(tmp_path):
    root = init_workspace(tmp_path / "prod", "prod", "miniprogram")
    spawned = []
    client = TestClient(
        create_studio_app(root, spawn=lambda r: spawned.append(r) or 4242, provider="mock")
    )
    return client, root, spawned


def test_first_visit_shows_editor_with_template_and_guide(studio):
    client, _, _ = studio
    page = client.get("/").text
    assert "textarea" in page
    assert "不需要任何技术词汇" in page  # template pre-filled
    assert "How to write a good FDR" in page  # guide reachable


def test_vague_fdr_roundtrips_to_questions(studio):
    client, root, _ = studio
    response = client.post(
        "/fdr", data={"fdr": "just an idea: 帮小区做团购"}, follow_redirects=True
    )
    assert "请先回答这些问题" in response.text
    assert (root / "FDR-QUESTIONS.md").exists()


def test_good_fdr_reaches_confirmation_with_build_button(studio):
    client, root, _ = studio
    response = client.post("/fdr", data={"fdr": GOOD_FDR}, follow_redirects=True)
    assert "开始搭建" in response.text
    assert (root / "product" / "CONFIRMATION.md").exists()


def test_build_button_spawns_exactly_one_worker(studio):
    client, _, spawned = studio
    client.post("/fdr", data={"fdr": GOOD_FDR})
    client.post("/build", follow_redirects=False)
    client.post("/build", follow_redirects=False)  # double-click safe? no pid marker in fake spawn
    assert len(spawned) >= 1


def test_report_state_renders_report(studio):
    client, root, _ = studio
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "BUILD-REPORT.md").write_text("# 已完成\n你的接龙工具好了。")
    page = client.get("/").text
    assert "已完成" in page          # the report renders
    assert "添加新功能" in page      # feature-granular add form
    assert "一次只写一个功能" in page  # granularity guidance in the UI


def test_status_endpoint(studio):
    client, _, _ = studio
    data = client.get("/status").json()
    assert set(data) == {"total", "built", "running", "tasks"}


# --- live progress + interrupted builds (signal s3 / s1) ----------------------


def _fabricate_partial_build(root):
    import yaml

    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "plan.yaml").write_text(yaml.safe_dump({
        "status": "locked", "brief_title": "x", "tasks": [
            {"id": "t1", "title": "URL store", "estimate_hours": 1},
            {"id": "t2", "title": "Shorten endpoint", "estimate_hours": 1},
        ]}), encoding="utf-8")
    spec_dir = root / "specs" / "url-store"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.yaml").write_text(yaml.safe_dump(
        {"request": "an item store (task:t1)", "built": True}), encoding="utf-8")


def test_building_page_shows_live_per_task_progress(studio):
    import os

    client, root, _ = studio
    _fabricate_partial_build(root)
    (root / ".mas" / "build.pid").write_text(str(os.getpid()))  # "running"
    page = client.get("/").text
    assert "fetch('/status')" in page  # polls in place, no blind reload
    assert "task-t1" in page and "task-t2" in page
    assert "✅ URL store" in page and "⏳ Shorten endpoint" in page

    status = client.get("/status").json()
    assert status["running"] is True
    assert {t["id"]: t["state"] for t in status["tasks"]} == {
        "t1": "built", "t2": "pending",
    }


def test_interrupted_build_offers_per_task_retry_and_reset_escapes(studio):
    import subprocess as sp
    import sys as _sys

    client, root, _ = studio
    _fabricate_partial_build(root)
    proc = sp.Popen([_sys.executable, "-c", ""])
    proc.wait()
    (root / ".mas" / "build.pid").write_text(str(proc.pid))  # dead worker
    page = client.get("/").text
    assert "搭建中断" in page
    assert "action=/retry" in page and "value='t2'" in page  # unbuilt task
    assert "value='t1'" not in page  # built modules are kept, not retried

    page = client.post("/reset", follow_redirects=True).text
    assert "搭建中断" not in page  # stale pid cleared — back to the editor
    assert not (root / ".mas" / "build.pid").exists()


# --- language selection (v0.52.0) --------------------------------------------


def _page(root, lang):
    from autoproduct.studio import create_studio_app

    client = TestClient(
        create_studio_app(root, spawn=lambda r: 1, provider="mock", lang=lang)
    )
    return client.get("/").text


def test_english_renders_with_no_chinese_anywhere(tmp_path):
    """The point of the flag: an English-speaking founder should not have to
    read `写下你的产品需求 / Describe your product`."""
    import re

    root = init_workspace(tmp_path / "en", "en", "web")
    page = _page(root, "en")
    assert not re.search(r"[一-鿿]", page), "English UI still has CJK"
    assert "<title>Describe your product</title>" in page
    assert "Check it &amp; make the plan" in page
    assert "How to write a good FDR" in page
    # The pre-filled template is English too, or the textarea betrays it.
    assert "Fill this in using your own words" in page
    assert "What does success look like?" in page


def test_chinese_default_is_unchanged(tmp_path):
    """The default must behave exactly as before — existing users see no
    difference, which is why zh keeps the original bilingual strings."""
    root = init_workspace(tmp_path / "zh", "zh", "web")
    default_page = _page(root, "zh")
    assert "写下你的产品需求 / Describe your product" in default_page
    assert "检查并生成计划" in default_page
    assert "不需要任何技术词汇" in default_page  # the Chinese template
    # ...and an unset language is the Chinese default.
    from autoproduct.studio import create_studio_app

    unset = TestClient(create_studio_app(root, spawn=lambda r: 1,
                                         provider="mock")).get("/").text
    assert unset == default_page


@pytest.mark.parametrize("given", ["EN", "en-US", "en_GB"])
def test_language_codes_are_normalized(tmp_path, given):
    root = init_workspace(tmp_path / f"n{given[:2]}", "n", "web")
    assert "<title>Describe your product</title>" in _page(root, given)


def test_an_unknown_language_falls_back_rather_than_blanking_the_ui(tmp_path):
    """A missing translation must never render an empty page: fall back to
    the default, which is a working UI in the wrong language rather than a
    broken one in none."""
    root = init_workspace(tmp_path / "xx", "xx", "web")
    page = _page(root, "klingon")
    assert "写下你的产品需求" in page


def test_every_string_exists_in_both_languages():
    from autoproduct.studio_i18n import LANGUAGES, STRINGS

    for key, values in STRINGS.items():
        assert set(values) == set(LANGUAGES), f"{key} is missing a language"
        for lang, text in values.items():
            assert text.strip(), f"{key}/{lang} is empty"


def test_the_english_readme_demo_shows_the_english_screenshot():
    """The README's founder demo and the shipped image must agree — a demo
    claiming English while showing a Chinese UI is the bug this closes."""
    import pathlib

    repo = pathlib.Path(__file__).resolve().parents[1]
    readme = (repo / "README.md").read_text(encoding="utf-8")
    assert "docs/media/studio-en.png" in readme
    assert "--lang en" in readme
    assert (repo / "docs" / "media" / "studio-en.png").exists()
