"""A successful retry must change what the founder sees.

`retry-task` rebuilt the module, committed the code — and never touched
product/outcomes.yaml. So the report and the Studio's "modules that did not
build" card went on listing it as failed, offering to retry something that
was already built. Observed: t5 and t9 committed at 21:41, outcomes.yaml
still stamped 21:02 saying spec_blocked.
"""
from __future__ import annotations

import yaml

from ai_venture_studio.cli import record_retry_outcome
from ai_venture_studio.upstream.build import BuildResult
from ai_venture_studio.upstream.plan import Task


def _task():
    return Task(id="t5", title="虚拟配送倒计时", description="d",
                depends_on=[], lane="core", estimate_hours=1)


def _outcomes(root):
    return yaml.safe_load((root / "product" / "outcomes.yaml").read_text()) or []


def test_a_successful_retry_flips_the_recorded_status(tmp_path):
    (tmp_path / "product").mkdir()
    (tmp_path / "product" / "outcomes.yaml").write_text(yaml.safe_dump([
        {"task_id": "t5", "title": "虚拟配送倒计时", "status": "spec_blocked"},
        {"task_id": "t2", "title": "other", "status": "built"},
    ]), encoding="utf-8")

    record_retry_outcome(
        tmp_path, _task(),
        BuildResult(slug="s", status="built", iterations=1,
                    files_written=["a.js"], test_summary="2 passed"),
    )

    rows = {r["task_id"]: r for r in _outcomes(tmp_path)}
    assert rows["t5"]["status"] == "built"
    assert rows["t5"]["files_written"] == ["a.js"]
    assert rows["t2"]["status"] == "built", "other rows must be untouched"
    assert len(rows) == 2, "the retried row is replaced, not appended"


def test_a_retry_that_blocks_again_records_the_new_reason(tmp_path):
    (tmp_path / "product").mkdir()
    (tmp_path / "product" / "outcomes.yaml").write_text(yaml.safe_dump([
        {"task_id": "t5", "title": "x", "status": "spec_blocked",
         "detail": "the OLD reason"},
    ]), encoding="utf-8")

    record_retry_outcome(tmp_path, _task(), None,
                         status="spec_blocked", detail="the NEW reason")

    row = _outcomes(tmp_path)[0]
    assert row["detail"] == "the NEW reason"


def test_it_creates_the_file_when_there_is_none(tmp_path):
    record_retry_outcome(
        tmp_path, _task(), BuildResult(slug="s", status="built"),
    )
    assert _outcomes(tmp_path)[0]["task_id"] == "t5"


def test_bookkeeping_never_fails_the_retry(tmp_path):
    """A build that succeeded must not be reported as failed because a
    yaml write went wrong."""
    blocked = tmp_path / "product"
    blocked.write_text("not a directory", encoding="utf-8")
    record_retry_outcome(tmp_path, _task(), BuildResult(slug="s", status="built"))
