"""Root conftest — session-scoped hooks only.

`pytest_sessionfinish` is one of the hooks pytest invokes **only** from the
rootdir conftest (or a plugin), never from a subdirectory one. It was written
into `tests/conftest.py` first and silently never ran: the suite passed 1667
against a PC-1 of 1655 and said nothing, which is the same class of quiet
non-enforcement this check exists to end.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "tests"))


def pytest_sessionfinish(session, exitstatus):
    """Measure PC-1 against the run that just happened (see tests/claim_count.py).

    Only on a whole-suite, unfiltered run — a subset would compare its own
    handful against the whole suite's claim, and subsets are what everyone runs
    all day. A mismatch fails the RELEASE run (`AVS_RELEASE_CHECK`, set by
    publish.yml at the tag, which is what PC-1's "at the current tag" means)
    and is reported loudly otherwise, because main drifting between releases is
    normal while a released number being fiction is not.
    """
    from claim_count import (
        RELEASE_ENV,
        claimed_test_count,
        is_whole_suite_run,
        verdict,
    )

    config = session.config
    if not is_whole_suite_run(
        config.args, config.option.keyword, config.option.markexpr, config.rootdir
    ):
        return
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    # A failing suite has a louder problem than a stale claim; don't bury it.
    if exitstatus != 0:
        return
    problem = verdict(len(reporter.stats.get("passed", [])), claimed_test_count())
    if problem is None:
        return
    reporter.write_line("")
    if os.environ.get(RELEASE_ENV):
        reporter.write_line("PC-1 SELF-CHECK FAILED: " + problem, red=True)
        session.exitstatus = 1
    else:
        reporter.write_line(
            "PC-1 drift (not fatal outside a release): " + problem, yellow=True
        )
