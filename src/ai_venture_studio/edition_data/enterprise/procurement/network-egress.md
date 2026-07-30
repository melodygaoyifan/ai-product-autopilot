# Network egress — the complete outbound list

Every host this tool can contact, what for, and the env var that
re-points or disables it. This is the firewall-allowlist answer your
network team asks for before the pilot (the practice GitHub Copilot's
enterprise docs established). Anything not on this list is a bug —
report it as one.

Proxies and TLS interception need no configuration: every HTTP client in
the tool honors `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` and the
standard CA-bundle vars (`SSL_CERT_FILE`, `SSL_CERT_DIR`) — there is no
`verify=False` anywhere in this codebase.

## Model APIs (the only mandatory egress)

| Default host | Purpose | Re-point / disable |
|---|---|---|
| `api.anthropic.com` | writer + Claude voter seats | `ANTHROPIC_BASE_URL` (+ `ANTHROPIC_AUTH_TOKEN` for gateways), or `AVS_ANTHROPIC_MODE=bedrock\|vertex\|foundry` to route via your AWS/GCP/Azure tenancy |
| `api.openai.com` | optional cross-family voter seat | `OPENAI_BASE_URL` (LiteLLM-style gateways, on-prem vLLM/NIM) |
| `api.x.ai` | optional voter seat | `XAI_BASE_URL` |
| `generativelanguage.googleapis.com` | optional voter seat | `GEMINI_BASE_URL` |

`avs review --provider mock` runs the whole pipeline with zero model
egress (calibration, demos, air-gap smoke tests).

## Forge (goes wherever your code lives)

`gh` and `glab` talk to the GitHub / GitLab host they are authenticated
against — github.com, GitHub Enterprise Server, gitlab.com, or your
self-managed GitLab. The tool adds no forge hosts of its own.

## Review-time analysis tools (each optional, each visibly degrading)

| Default host | Trigger | Re-point / disable |
|---|---|---|
| `pypi.org` | slopsquat dependency check on diffs that add packages | `AVS_PYPI_JSON_BASE` → your Artifactory/Nexus (same `/pypi/<name>/json` shape); offline it reports `error`, never fails the review |
| `semgrep.dev` | only if semgrep is installed and no config pinned | `AVS_SEMGREP_CONFIG` → a local ruleset path or internal mirror; metrics are always `--metrics=off` |
| OSV / PyPI via `pip-audit` | only if pip-audit is installed | skip by not installing it — absence reports `skipped`, never silence |
| your index via `uv pip install` | product-bench probe venvs | honors `UV_INDEX_URL` / `PIP_INDEX_URL` |
| Playwright browser CDN | only with the `[screenshots]` extra, at `playwright install` time | `PLAYWRIGHT_DOWNLOAD_HOST` → internal mirror; the base install has no playwright at all |

## Only if you configure them

Monitoring intake (Sentry/Datadog/PagerDuty base URLs are env-overridable
and used only when a signal source is declared), `SCHEMA_REGISTRY_URL`
(skipped when unset), and operator-declared market probes (each requires
standing in `.mas/signal-sources.yaml`; agents cannot fetch).

## Never

Telemetry: opt-in, aggregate-only, and this version configures **no
endpoint** — nothing sends. There are no update checks, no license
pings, and import time performs zero network I/O (tree-sitter grammars
ship inside the wheel). Credentials can arrive as K8s/Docker secret
mounts via `<VAR>_FILE` and never appear in prompts or logs.
