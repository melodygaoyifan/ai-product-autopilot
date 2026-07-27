from ai_venture_studio.diff import parse_unified_diff
from ai_venture_studio.tools import external, probes


def _diff(path: str, *added: str) -> str:
    body = "\n".join(f"+{line}" for line in added)
    return (
        f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
        f"@@ -1,0 +1,{len(added)} @@\n{body}\n"
    )


def test_secret_scan_catches_aws_key():
    diff = parse_unified_diff(_diff("config.py", 'AWS_KEY = "AKIAIOSFODNN7REALKEY"'))
    report = probes.secret_scan(diff, ".")
    assert len(report.findings) == 1
    assert report.findings[0].severity.value == "critical"
    assert report.findings[0].verification == "VERIFIED"


def test_secret_scan_skips_placeholder_assignment_values():
    diff = parse_unified_diff(
        _diff("tests/conftest.py", 'SECRET = "test-webhook-secret-value"')
    )
    assert probes.secret_scan(diff, ".").findings == []


def test_secret_scan_still_catches_realistic_assignments():
    diff = parse_unified_diff(
        _diff("config.py", 'API_KEY = "kJ9mPq2xVn8LwRt5YbCd3FgH"')
    )
    assert len(probes.secret_scan(diff, ".").findings) == 1


def test_secret_scan_skips_documentation_example_keys():
    diff = parse_unified_diff(_diff("config.py", 'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"'))
    assert probes.secret_scan(diff, ".").findings == []


def test_csrf_ssrf_probe_ignores_data_files():
    diff = parse_unified_diff(
        _diff("benchmarks/cases/08.yaml", "    resp = requests.get(callback_url)")
    )
    assert probes.csrf_ssrf_probe(diff, ".").findings == []


def test_secret_scan_clean_diff():
    diff = parse_unified_diff(_diff("config.py", "DEBUG = False"))
    assert probes.secret_scan(diff, ".").findings == []


def test_csrf_probe_flags_unprotected_endpoint():
    diff = parse_unified_diff(
        _diff("views.py", '@app.post("/orders/cancel")', "def cancel(): ...")
    )
    report = probes.csrf_ssrf_probe(diff, ".")
    assert any("CSRF" in f.title for f in report.findings)


def test_csrf_probe_quiet_when_protection_visible():
    diff = parse_unified_diff(
        _diff("views.py", '@app.post("/x")', "@csrf_protect", "def x(): ...")
    )
    assert probes.csrf_ssrf_probe(diff, ".").findings == []


def test_ssrf_probe_flags_variable_url():
    diff = parse_unified_diff(_diff("client.py", "resp = requests.get(user_url)"))
    report = probes.csrf_ssrf_probe(diff, ".")
    assert any("SSRF" in f.title for f in report.findings)


def test_csrf_ssrf_probe_skips_test_support_files():
    """Test clients hit variable localhost URLs by design — flagging them
    buried runs 7-9's reviews in SSRF noise (clean reviews pinned at 0%)."""
    for path in ("tests/helpers.py", "tests/test_client.py", "conftest.py",
                 "app/tests/conftest.py"):
        diff = parse_unified_diff(_diff(path, "resp = requests.get(base_url)"))
        assert probes.csrf_ssrf_probe(diff, ".").findings == [], path
    # Production code stays flagged.
    diff = parse_unified_diff(_diff("app/client.py", "resp = requests.get(u)"))
    assert probes.csrf_ssrf_probe(diff, ".").findings != []


def test_ssrf_probe_allows_literal_url():
    diff = parse_unified_diff(
        _diff("client.py", 'resp = requests.get("https://api.example.com/v1")')
    )
    assert probes.csrf_ssrf_probe(diff, ".").findings == []


def _dep_diff(*lines: str) -> str:
    return _diff("requirements.txt", *lines)


def test_slopsquat_nonexistent_package():
    diff = parse_unified_diff(_dep_diff("definitely-hallucinated-pkg==1.0"))
    report = probes.slopsquat_check(diff, ".", fetcher=lambda name: None)
    assert len(report.findings) == 1
    assert "does not exist" in report.findings[0].title


def test_slopsquat_typosquat_detected_without_registry():
    calls = []
    diff = parse_unified_diff(_dep_diff("reqeusts==2.0"))
    report = probes.slopsquat_check(
        diff, ".", fetcher=lambda name: calls.append(name)
    )
    assert "typosquat" in report.findings[0].title
    assert calls == []  # typosquat verdict needs no network


def test_slopsquat_young_package_flagged():
    diff = parse_unified_diff(_dep_diff("brand-new-pkg==0.1"))
    report = probes.slopsquat_check(
        diff, ".", fetcher=lambda name: {"first_upload_days": 5}
    )
    assert "<30 days" in report.findings[0].title


def test_slopsquat_established_package_clean():
    diff = parse_unified_diff(_dep_diff("requests>=2.31"))
    report = probes.slopsquat_check(
        diff, ".", fetcher=lambda name: {"first_upload_days": 4000}
    )
    assert report.findings == []


def test_external_tools_skip_when_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    diff = parse_unified_diff(_diff("a.py", "x = 1"))
    for runner in (external.semgrep, external.bandit, external.pip_audit, external.trufflehog):
        report = runner(diff, ".")
        assert report.status == "skipped"
        assert "not installed" in report.detail


def test_bandit_b310_skipped_on_test_files(monkeypatch, tmp_path):
    """B310 (urllib.urlopen audit) on a test file flags the suite's own
    localhost client — run 11: 30 of 44 review findings were this one
    check. Production files keep the full audit; other MEDIUM findings
    on test files still report."""
    import json as _json
    import shutil as _shutil

    from ai_venture_studio.tools import external

    (tmp_path / "tests").mkdir()
    (tmp_path / "app").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("import urllib.request\n")
    (tmp_path / "app" / "client.py").write_text("import urllib.request\n")
    diff = parse_unified_diff(
        _diff("tests/test_x.py", "import urllib.request")
        + _diff("app/client.py", "import urllib.request")
    )
    results = {"results": [
        {"filename": "tests/test_x.py", "line_number": 1, "test_id": "B310",
         "test_name": "blacklist", "issue_severity": "MEDIUM",
         "issue_text": "urlopen audit", "code": "urllib.request.urlopen(u)"},
        {"filename": "app/client.py", "line_number": 1, "test_id": "B310",
         "test_name": "blacklist", "issue_severity": "MEDIUM",
         "issue_text": "urlopen audit", "code": "urllib.request.urlopen(u)"},
        {"filename": "tests/test_x.py", "line_number": 1, "test_id": "B608",
         "test_name": "hardcoded_sql", "issue_severity": "MEDIUM",
         "issue_text": "sql", "code": "q"},
    ]}
    monkeypatch.setattr(_shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(external, "_run_json", lambda cmd, cwd: (_json.dumps(results), ""))
    report = external.bandit(diff, str(tmp_path))
    flagged = {(f.file_path, f.title.split(":")[0]) for f in report.findings}
    assert ("app/client.py", "B310") in flagged      # production keeps the audit
    assert ("tests/test_x.py", "B608") in flagged    # other MEDIUMs on tests stay
    assert ("tests/test_x.py", "B310") not in flagged
