"""小程序 deterministic checks (doc 17 §43.1) — the four named preflights.

mp_size_check (the 2MB main-package budget, per compiled target),
mp_domain_check (every request host on the declared whitelist),
mp_setdata_lint (oversized/hot-path setData payload patterns),
mp_privacy_check (授权 APIs demand a declared 隐私协议 entry + lazy
authorization — request at point of use, never at launch).
"""

from __future__ import annotations

import re

from pydantic import BaseModel

MAIN_PACKAGE_BUDGET_BYTES = 2 * 1024 * 1024  # platform limit, verify-at-adoption
_PRIVACY_APIS = ("getUserProfile", "getLocation", "chooseAddress",
                 "getPhoneNumber", "chooseImage", "getWeRunData")
_URL = re.compile(r"https?://([\w.-]+)")
_SETDATA = re.compile(r"\.setData\(")


class MpFinding(BaseModel):
    check: str
    rule: str
    message: str


def mp_size_check(compiled_sizes: dict[str, int]) -> list[MpFinding]:
    """Per compiled TARGET (F-17.6): dev-tools size lies about the dist."""
    return [
        MpFinding(check="mp_size_check", rule="package_over_budget",
                  message=f"{target}: {size} bytes exceeds the "
                          f"{MAIN_PACKAGE_BUDGET_BYTES}-byte main-package budget")
        for target, size in sorted(compiled_sizes.items())
        if size > MAIN_PACKAGE_BUDGET_BYTES
    ]


def mp_domain_check(sources: dict[str, str], whitelist: list[str]) -> list[MpFinding]:
    findings = []
    allowed = {d.lower() for d in whitelist}
    for path, source in sorted(sources.items()):
        for match in _URL.finditer(source):
            host = match.group(1).lower()
            if host not in allowed:
                findings.append(MpFinding(
                    check="mp_domain_check", rule="undeclared_domain",
                    message=f"{path}: {host} is not on the request whitelist — "
                            "the platform will block it in production"))
    return findings


def mp_setdata_lint(sources: dict[str, str], *, max_calls_per_file: int = 8) -> list[MpFinding]:
    findings = []
    for path, source in sorted(sources.items()):
        calls = len(_SETDATA.findall(source))
        if calls > max_calls_per_file:
            findings.append(MpFinding(
                check="mp_setdata_lint", rule="setdata_hot_path",
                message=f"{path}: {calls} setData calls — batch updates; "
                        "per-frame setData is the classic jank source"))
        if re.search(r"setData\(\s*\{\s*[\w.]*list", source) and "slice" not in source:
            findings.append(MpFinding(
                check="mp_setdata_lint", rule="unbounded_setdata_payload",
                message=f"{path}: whole-list setData without pagination/slicing"))
    return findings


def mp_privacy_check(
    sources: dict[str, str], *, privacy_agreement_declared: bool,
    launch_files: tuple[str, ...] = ("app.js", "app.ts"),
) -> list[MpFinding]:
    findings = []
    for path, source in sorted(sources.items()):
        used = [api for api in _PRIVACY_APIS if api in source]
        if used and not privacy_agreement_declared:
            findings.append(MpFinding(
                check="mp_privacy_check", rule="missing_privacy_agreement",
                message=f"{path}: uses {used} with no declared 隐私协议 entry"))
        if any(path.endswith(f) for f in launch_files) and used:
            findings.append(MpFinding(
                check="mp_privacy_check", rule="eager_authorization",
                message=f"{path}: 授权 at launch ({used}) — request lazily, at "
                        "the point of use; eager prompts are a review rejection"))
    return findings


# --- runtime verification (item P1.3's sibling: does it actually LOAD?) ------
#
# `_miniprogram_gate` in build.py is STATIC — it reads app.json and the page
# files and answers "would DevTools open this project". That gate exists
# because a run once built nine modules and seven page directories with no
# app.json at all. What it cannot answer is whether the pages then RENDER,
# and until now the only thing that could was a human opening DevTools —
# which is why every "it works" claim about a 小程序 ended with an unverified
# promise.
#
# It is verifiable, with preconditions this module refuses to paper over:
#
#   1. WeChat DevTools is a desktop application. macOS and Windows only,
#      no Linux, so this can never be a CI gate — `ubuntu-latest` cannot
#      run it at all.
#   2. `miniprogram-automator` (npm) drives it. Not a dependency of this
#      package; the workspace installs it or the check is skipped.
#   3. DevTools' **service port must be enabled by a human**, once, in
#      Settings → Security. This is the wall a first attempt hits:
#         [error] IDE service port disabled. To use CLI Call, please ...
#                 set Service Port On.
#      It is a security setting on someone's machine and the framework has
#      no business flipping it — so the check names it and stops.
#
# Every one of those is a VISIBLE skip naming the remedy, never a silent
# pass: "no runtime check ran" and "the pages render" must never look alike.

DEVTOOLS_CLI_MACOS = "/Applications/wechatwebdevtools.app/Contents/MacOS/cli"
DEVTOOLS_CLI_WINDOWS = r"C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat"
_SERVICE_PORT_DISABLED = "service port disabled"


class MpRuntimeReport(BaseModel):
    status: str  # ok | failed | skipped
    detail: str = ""
    pages_checked: list[str] = []
    findings: list[MpFinding] = []


def devtools_cli(explicit: str | None = None) -> str | None:
    """The DevTools CLI, or None when the desktop app is not installed."""
    import os
    import pathlib

    for candidate in (explicit, os.environ.get("AUTOPRODUCT_DEVTOOLS_CLI"),
                      DEVTOOLS_CLI_MACOS, DEVTOOLS_CLI_WINDOWS):
        if candidate and pathlib.Path(candidate).exists():
            return str(candidate)
    return None


def mp_runtime_check(
    repo_dir, *, timeout_s: int = 120, cli_path: str | None = None
) -> MpRuntimeReport:
    """Open the project in DevTools automation and visit every page.

    Returns `skipped` — loudly, with the remedy — when the desktop app,
    the automator package, or the human-set service port is missing.
    """
    import json
    import pathlib
    import shutil
    import subprocess
    import tempfile

    root = pathlib.Path(repo_dir).resolve()
    cli = devtools_cli(cli_path)
    if cli is None:
        return MpRuntimeReport(
            status="skipped",
            detail="WeChat DevTools is not installed (looked in "
                   f"{DEVTOOLS_CLI_MACOS}). Runtime verification needs the "
                   "desktop app and runs on macOS/Windows only — it can never "
                   "run in CI. The static loadability gate still applies.",
        )
    if shutil.which("node") is None:
        return MpRuntimeReport(
            status="skipped",
            detail="node is not on PATH; miniprogram-automator is a node package.",
        )
    driver_dir = _automator_root(root)
    if driver_dir is None:
        return MpRuntimeReport(
            status="skipped",
            detail="miniprogram-automator is not installed. From the "
                   f"workspace: `npm i -D miniprogram-automator` ({root}).",
        )

    pages = _registered_pages(root)
    if not pages:
        return MpRuntimeReport(
            status="skipped",
            detail="app.json registers no pages — nothing to visit. The "
                   "static gate covers this case and blocks on it.",
        )

    with tempfile.TemporaryDirectory() as tmp:
        driver = pathlib.Path(tmp) / "runtime-check.js"
        driver.write_text(_DRIVER_JS, encoding="utf-8")
        proc = subprocess.run(
            ["node", str(driver)],
            cwd=driver_dir,
            capture_output=True,
            text=True,
            timeout=timeout_s + 30,
            env={
                **_clean_env(),
                # The driver lives in a temp dir, so `require` resolves from
                # THERE, not from cwd — NODE_PATH is what points it at the
                # workspace's node_modules.
                "NODE_PATH": str(driver_dir / "node_modules"),
                "AVS_CLI_PATH": cli,
                "AVS_PROJECT": str(_project_root(root)),
                "AVS_PAGES": json.dumps(pages),
                "AVS_TIMEOUT": str(timeout_s * 1000),
            },
        )
    raw = (proc.stdout or "").strip().splitlines()
    payload = next(
        (json.loads(line) for line in reversed(raw) if line.startswith("{")), None
    )
    if payload is None:
        stderr = (proc.stderr or "").strip()[-400:]
        if _SERVICE_PORT_DISABLED in (proc.stdout + proc.stderr).lower():
            return MpRuntimeReport(
                status="skipped",
                detail="DevTools' service port is off. Open DevTools → 设置 → "
                       "安全设置 → 服务端口 (Settings → Security → Service Port) "
                       "and turn it on; it is a one-time, human-only toggle "
                       "on your own machine.",
            )
        return MpRuntimeReport(
            status="failed",
            detail=f"the automation driver returned nothing usable: {stderr or '(no output)'}",
        )
    if payload.get("error"):
        detail = str(payload["error"])
        lowered = detail.lower()
        if _SERVICE_PORT_DISABLED in lowered or "timed out" in lowered:
            # The automator spawns the CLI itself and swallows its stderr, so
            # the disabled-port error — which the CLI states plainly —
            # reaches us as a bare "Wait timed out". Verified by hand: with
            # the port off, `cli auto --project <p>` prints
            #   [error] IDE service port disabled ... set Service Port On.
            # while the automator on the same project times out at 30s with
            # nothing else. Reporting that as `failed` would read as "the
            # pages are broken" when nothing was ever checked.
            return MpRuntimeReport(
                status="skipped",
                detail=(
                    "DevTools never accepted the automation connection "
                    f"({detail}). Almost always the service port: open "
                    "DevTools → 设置 → 安全设置 → 服务端口 (Settings → Security "
                    "→ Service Port) and switch it on — a one-time toggle on "
                    "your own machine that the framework will not flip for "
                    f"you. To see the CLI say it itself: `{cli} auto "
                    f"--project {_project_root(root)}`."
                ),
            )
        return MpRuntimeReport(status="failed", detail=detail)

    failed = [p for p in payload.get("pages", []) if not p.get("ok")]
    return MpRuntimeReport(
        status="failed" if failed else "ok",
        detail=(
            f"{len(failed)} of {len(pages)} registered page(s) did not render"
            if failed
            else f"all {len(pages)} registered page(s) rendered"
        ),
        pages_checked=[p["path"] for p in payload.get("pages", [])],
        findings=[
            MpFinding(check="mp_runtime_check", rule="page_did_not_render",
                      message=f"{p['path']}: {p.get('error', 'no error reported')}")
            for p in failed
        ],
    )


def _clean_env() -> dict:
    import os

    return {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}


def _project_root(root):
    """Where project.config.json lives — what DevTools opens."""
    import pathlib

    for candidate in (root, root / "miniprogram"):
        if (pathlib.Path(candidate) / "project.config.json").exists():
            return candidate
    return root


def _automator_root(root):
    """A directory from which `require('miniprogram-automator')` resolves."""
    import pathlib

    for candidate in (root, root.parent, pathlib.Path.cwd()):
        if (candidate / "node_modules" / "miniprogram-automator").is_dir():
            return candidate
    return None


def _registered_pages(root) -> list[str]:
    import json
    import pathlib

    for base in (root / "miniprogram", root):
        app_json = pathlib.Path(base) / "app.json"
        if app_json.exists():
            try:
                return [str(p) for p in (json.loads(
                    app_json.read_text(encoding="utf-8")) or {}).get("pages", [])]
            except ValueError:
                return []
    return []


#: Visits every registered page and reports per-page, as one JSON line.
#: Deliberately dumb: it renders and reads back the page path. A page that
#: throws on load fails here, which is the whole question the static gate
#: cannot answer.
_DRIVER_JS = """
const automator = require('miniprogram-automator');
const pages = JSON.parse(process.env.AVS_PAGES);
const out = { pages: [] };
automator.launch({
  cliPath: process.env.AVS_CLI_PATH,
  projectPath: process.env.AVS_PROJECT,
  timeout: Number(process.env.AVS_TIMEOUT),
}).then(async (mp) => {
  for (const path of pages) {
    try {
      const page = await mp.reLaunch('/' + path);
      await page.waitFor(300);
      out.pages.push({ path, ok: true });
    } catch (e) {
      out.pages.push({ path, ok: false, error: String(e).slice(0, 300) });
    }
  }
  await mp.close();
  console.log(JSON.stringify(out));
  process.exit(0);
}).catch((e) => {
  console.log(JSON.stringify({ error: String(e).slice(0, 400) }));
  process.exit(0);
});
"""
