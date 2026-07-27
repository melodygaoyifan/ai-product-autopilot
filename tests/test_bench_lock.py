"""Product-bench single-instance lock (2026-07-26: two sessions launched
run 6 concurrently — same log, same workspace paths, doubled spend)."""

import os
import subprocess
import sys

import pytest

from ai_venture_studio.product_bench import (
    acquire_bench_lock,
    release_bench_lock,
    run_product_bench,
)


def _dead_pid() -> int:
    """Spawn and reap a child; its pid no longer exists."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=30)
    return proc.pid


def test_acquire_release_roundtrip(tmp_path):
    pidfile = acquire_bench_lock(tmp_path)
    assert pidfile.read_text() == str(os.getpid())
    release_bench_lock(pidfile)
    assert not pidfile.exists()


def test_second_bench_is_refused_while_first_is_alive(tmp_path):
    pidfile = tmp_path / ".mas" / "product-bench" / "bench.pid"
    pidfile.parent.mkdir(parents=True)
    pidfile.write_text("1")  # pid 1 always exists and is never ours
    with pytest.raises(RuntimeError, match="already running"):
        acquire_bench_lock(tmp_path)
    with pytest.raises(RuntimeError, match="already running"):
        run_product_bench(tmp_path / "no-cases", repo_dir=tmp_path)
    assert pidfile.read_text() == "1"  # loser must not steal the lock


def test_stale_pidfile_is_reclaimed(tmp_path):
    pidfile = tmp_path / ".mas" / "product-bench" / "bench.pid"
    pidfile.parent.mkdir(parents=True)
    pidfile.write_text(str(_dead_pid()))
    acquired = acquire_bench_lock(tmp_path)
    assert acquired.read_text() == str(os.getpid())
    release_bench_lock(acquired)


def test_lock_released_even_when_bench_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_product_bench(tmp_path / "no-cases", repo_dir=tmp_path)
    assert not (tmp_path / ".mas" / "product-bench" / "bench.pid").exists()
