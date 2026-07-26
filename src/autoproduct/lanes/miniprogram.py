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
