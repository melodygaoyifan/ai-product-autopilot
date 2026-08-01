from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SKILLS = Path(__file__).parent.parent / "skills"


@pytest.fixture(autouse=True)
def _drain_spend_buffer():
    """Spend is recorded into a process-global buffer and flushed by whoever
    knows the workspace — which makes it shared state between tests.

    Without this, a test that records a call and never flushes leaves those
    rows in the buffer, and the NEXT test's `spend.flush(its_own_workspace)`
    writes them into that workspace's ledger. Found by a cost-cap test whose
    exact total passed alone and failed in the suite: the extra dollars came
    from a provider-contract test three files away.
    """
    from ai_venture_studio import spend

    with spend._lock:
        spend._buffer.clear()
    yield
    with spend._lock:
        spend._buffer.clear()


@pytest.fixture
def planted_diff_text() -> str:
    return (FIXTURES / "planted_bugs.diff").read_text()


@pytest.fixture
def skills_dir() -> str:
    return str(SKILLS)
