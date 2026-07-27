"""Backend↔frontend wire-up gate for the Founder Studio.

Every path the rendered HTML references — form actions, fetch() calls,
links, image sources — must resolve to a registered route with the right
method, and every route must be referenced by some rendered state: a dead
button and an orphaned endpoint are the same bug, drift between the two
halves of one feature. (The product-side analog is tools/wireup.py, which
does this for generated frontends against generated backends.)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

import pytest
import yaml
from fastapi.testclient import TestClient

from ai_venture_studio.studio import create_studio_app
from ai_venture_studio.upstream import init_workspace

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

_FORM_ACTION = re.compile(r"action=['\"]?(/[^'\" >]*)")
_FETCH = re.compile(r"fetch\(['\"](/[^'\"]+)['\"]\)")
_HREF = re.compile(r"href=['\"](/[^'\"]+)['\"]")
_SRC = re.compile(r"src=['\"](/[^'\"]+)['\"]")


def _routes(app) -> dict[str, set[str]]:
    table: dict[str, set[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods:
            table.setdefault(path, set()).update(m for m in methods if m != "HEAD")
    return table


def _resolves(path: str, route: str) -> bool:
    parts, route_parts = path.split("/"), route.split("/")
    return len(parts) == len(route_parts) and all(
        r.startswith("{") or p == r for p, r in zip(parts, route_parts)
    )


def _route_for(path: str, table: dict[str, set[str]]) -> str | None:
    for route in table:
        if _resolves(path, route):
            return route
    return None


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", ""])
    proc.wait()
    return proc.pid


@pytest.fixture
def studio(tmp_path):
    root = init_workspace(tmp_path / "prod", "prod", "web")
    client = TestClient(create_studio_app(root, spawn=lambda r: 4242, provider="mock"))
    return client, root


def _walk_all_states(client, root) -> dict[str, list[tuple[str, str]]]:
    """Render every Studio state and collect (method, path) references."""
    pages: list[str] = []

    def snap():
        pages.append(client.get("/").text)

    # 1. FDR editor (fresh workspace).
    snap()

    # 2. Plan-confirmation state.
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "CONFIRMATION.md").write_text("plan", encoding="utf-8")
    snap()

    # 3. Building (live worker) — polls /status.
    (root / "product" / "plan.yaml").write_text(yaml.safe_dump({
        "status": "locked", "brief_title": "x", "tasks": [
            {"id": "t1", "title": "one", "estimate_hours": 1},
            {"id": "t2", "title": "two", "estimate_hours": 1},
        ]}), encoding="utf-8")
    spec_dir = root / "specs" / "one"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.yaml").write_text(
        yaml.safe_dump({"request": "one (task:t1)", "built": True}), encoding="utf-8"
    )
    (root / ".mas" / "build.pid").write_text(str(os.getpid()))
    snap()

    # 4. Interrupted (dead worker, no report yet).
    (root / ".mas" / "build.pid").write_text(str(_dead_pid()))
    snap()

    # 5. Feature awaiting confirmation (renders before the report page).
    (root / "product" / "BUILD-REPORT.md").write_text("# done", encoding="utf-8")
    (root / "product" / "ACCEPTANCE.md").write_text("check", encoding="utf-8")
    shots = root / "product" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    (shots / "home.png").write_bytes(b"\x89PNG\r\n")
    (root / "product" / "outcomes.yaml").write_text(yaml.safe_dump(
        [{"task_id": "t1", "title": "one", "status": "built"},
         {"task_id": "t2", "title": "two", "status": "build_failed"}]
    ), encoding="utf-8")
    pending = root / "product" / "features" / "f2-cancel-orders"
    pending.mkdir(parents=True, exist_ok=True)
    (pending / "CONFIRMATION.md").write_text("new feature", encoding="utf-8")
    snap()

    # 6. Full product/report page (feature confirmed → built).
    (pending / "REPORT.md").write_text("built", encoding="utf-8")
    snap()

    # 7. Acceptance walkthrough page.
    pages.append(client.get("/acceptance").text)

    refs: dict[str, list[tuple[str, str]]] = {"POST": [], "GET": []}
    for page in pages:
        for path in _FORM_ACTION.findall(page):
            refs["POST"].append((path, page[:60]))
        for pattern in (_FETCH, _HREF, _SRC):
            for path in pattern.findall(page):
                refs["GET"].append((path, page[:60]))
    return refs


def test_every_frontend_reference_resolves_to_a_backend_route(studio):
    client, root = studio
    table = _routes(client.app)
    refs = _walk_all_states(client, root)
    assert refs["POST"] and refs["GET"], "state walk rendered no references"
    for method in ("POST", "GET"):
        for path, _context in refs[method]:
            route = _route_for(path, table)
            assert route is not None, f"frontend references {path} — no route"
            assert method in table[route], (
                f"frontend uses {method} {path} but the route allows {table[route]}"
            )


def test_every_backend_route_is_reachable_from_some_rendered_state(studio):
    client, root = studio
    table = _routes(client.app)
    refs = _walk_all_states(client, root)
    referenced = {p for pairs in refs.values() for p, _ in pairs} | {"/"}
    for route, methods in table.items():
        hit = any(_resolves(path, route) for path in referenced)
        assert hit, (
            f"route {route} ({sorted(methods)}) is rendered by no Studio state — "
            "orphaned endpoint or missing UI"
        )


def test_status_payload_matches_what_the_building_page_js_reads(studio):
    """The building page's script reads s.running / s.built / s.total and
    t.id / t.title / t.state per task — the JSON contract, pinned."""
    client, root = studio
    (root / "product").mkdir(exist_ok=True)
    (root / "product" / "plan.yaml").write_text(yaml.safe_dump({
        "status": "locked", "brief_title": "x",
        "tasks": [{"id": "t1", "title": "one", "estimate_hours": 1}],
    }), encoding="utf-8")
    data = client.get("/status").json()
    assert set(data) == {"total", "built", "running", "tasks"}
    assert all(set(t) == {"id", "title", "state"} for t in data["tasks"])
    page_src = client.get("/").text  # editor state — no script, but the
    # building page's JS is source-checked here so a rename fails loudly:
    from ai_venture_studio import studio as studio_mod
    import inspect

    src = inspect.getsource(studio_mod)
    for token in ("s.running", "s.built", "s.total", "t.state", "t.title", "'task-'+t.id"):
        assert token in src, f"building-page JS no longer reads {token}"
    assert page_src  # the walk above already covers rendering
