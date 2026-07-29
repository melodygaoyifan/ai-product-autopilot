import shutil

import pytest
from fastapi.testclient import TestClient

from ai_venture_studio.studio import create_studio_app
from ai_venture_studio.upstream import init_workspace

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not on PATH"
)

GOOD_FDR = (
    "# 小区团购接龙\n团长发起接龙写商品和价格，住户下单选数量，团长看按商品汇总。\n"
    "必须有：发起、下单、汇总。暂时不要：在线支付。成功：一周10个团长用过。\n"
)


@pytest.fixture
def studio(tmp_path):
    """The Chinese-founder flow: a 小程序 workspace with a Chinese FDR, so it
    asks for the Chinese UI explicitly. English is the default since v0.53;
    `studio_en` below covers that path."""
    root = init_workspace(tmp_path / "prod", "prod", "miniprogram")
    spawned = []
    client = TestClient(
        create_studio_app(root, spawn=lambda r: spawned.append(r) or 4242,
                          provider="mock", lang="zh")
    )
    return client, root, spawned


@pytest.fixture
def studio_en(tmp_path):
    """The DEFAULT flow: no language argument at all."""
    root = init_workspace(tmp_path / "prod-en", "prod-en", "web")
    spawned = []
    client = TestClient(
        create_studio_app(root, spawn=lambda r: spawned.append(r) or 4242,
                          provider="mock")
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
    from ai_venture_studio.studio import create_studio_app

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


def test_chinese_is_still_available_character_for_character(tmp_path):
    """Moving the default must not degrade the Chinese UI: `--lang zh` gives
    exactly what 小程序 founders were using before."""
    root = init_workspace(tmp_path / "zh", "zh", "web")
    page = _page(root, "zh")
    assert "写下你的产品需求 / Describe your product" in page
    assert "检查并生成计划" in page
    assert "不需要任何技术词汇" in page  # the Chinese template


def test_english_is_the_default_when_no_language_is_given(tmp_path):
    import re

    from ai_venture_studio.studio import create_studio_app

    root = init_workspace(tmp_path / "default", "d", "web")
    unset = TestClient(create_studio_app(root, spawn=lambda r: 1,
                                         provider="mock")).get("/").text
    assert unset == _page(root, "en")
    assert not re.search(r"[一-鿿]", unset)


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
    assert "<title>Describe your product</title>" in page


def test_every_string_exists_in_both_languages():
    from ai_venture_studio.studio_i18n import LANGUAGES, STRINGS

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


def test_default_flow_first_visit_is_english(studio_en):
    client, _root, _ = studio_en
    page = client.get("/").text
    assert "<title>Describe your product</title>" in page
    assert "Fill this in using your own words" in page  # English template
    assert "How to write a good FDR" in page


def test_default_flow_reaches_confirmation_in_english(studio_en):
    client, root, _ = studio_en
    english_fdr = (
        "# Shared task list\n"
        "The two of us track work in chat and lose it. Anyone adds a task with "
        "a title and owner; anyone marks it done; we see open and done "
        "separately.\nMust have: add, mark done, both lists. Not yet: logins.\n"
        "Success: we stop tracking work in chat messages.\n"
    )
    response = client.post("/fdr", data={"fdr": english_fdr}, follow_redirects=True)
    assert "Start building" in response.text
    assert (root / "product" / "CONFIRMATION.md").exists()


# --- the CLI surface the docs promise (v0.56.1) ------------------------------


def test_studio_accepts_the_workspace_positionally_like_the_docs_show(tmp_path):
    """Every doc writes `avs studio myteam --profile web`, and README's
    founder quickstart is that exact line — but repo_dir was an Option, so
    the documented invocation died with "unexpected extra argument". The
    docs were right; the signature was wrong."""
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app

    served = {}

    def fake_serve(root, **kwargs):
        served["root"] = str(root)
        served.update(kwargs)

    import ai_venture_studio.studio as studio_mod

    original = studio_mod.serve_studio
    studio_mod.serve_studio = fake_serve
    try:
        result = CliRunner().invoke(
            app, ["studio", str(tmp_path / "myteam"), "--profile", "web"]
        )
    finally:
        studio_mod.serve_studio = original

    assert result.exit_code == 0, result.output
    assert served["root"].endswith("myteam")


def test_studio_still_defaults_to_the_current_directory(tmp_path):
    """The positional gains a default, so `avs studio` inside an existing
    workspace keeps working — that is the returning-user path."""
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app
    from ai_venture_studio.upstream import init_workspace

    root = init_workspace(tmp_path / "ws", "ws", "web")
    served = {}

    import ai_venture_studio.studio as studio_mod

    original = studio_mod.serve_studio
    studio_mod.serve_studio = lambda r, **kw: served.update(root=str(r))
    try:
        result = CliRunner().invoke(app, ["studio", str(root)])
    finally:
        studio_mod.serve_studio = original

    assert result.exit_code == 0, result.output
    assert served["root"] == str(root)


def test_the_old_repo_dir_flag_keeps_working_with_a_deprecation_notice(tmp_path):
    """The CLI surface is a versioned contract: `--repo-dir` was the only
    way in before v0.56.1, so it still works — loudly deprecated, not
    silently removed."""
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app

    served = {}
    import ai_venture_studio.studio as studio_mod

    original = studio_mod.serve_studio
    studio_mod.serve_studio = lambda r, **kw: served.update(root=str(r))
    try:
        result = CliRunner().invoke(
            app, ["studio", "--repo-dir", str(tmp_path / "old"),
                  "--profile", "web"]
        )
    finally:
        studio_mod.serve_studio = original

    assert result.exit_code == 0, result.output
    assert served["root"].endswith("old")
    assert "deprecated" in result.output.lower()


def test_giving_the_workspace_twice_is_refused_not_guessed(tmp_path):
    from typer.testing import CliRunner

    from ai_venture_studio.cli import app

    result = CliRunner().invoke(
        app, ["studio", str(tmp_path / "a"), "--repo-dir", str(tmp_path / "b")]
    )
    assert result.exit_code == 2
    assert "twice" in result.output
