"""CI-triggered reviews — the webhook-less enterprise entry point.

Locked-down enterprises often cannot expose a webhook endpoint at all;
the standard pattern is running the reviewer as a pipeline job on the
merge request itself, with the forge token injected as a CI variable.
`avs review --from-ci` derives the review target from the CI system's
predefined variables, so the pipeline step is one line and needs no
public surface.

Detection is deliberately explicit per CI system: a CI environment we
can name but not support says so, and no CI environment at all is an
error — never a silent fall-through to reviewing the wrong thing.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


class CITargetError(RuntimeError):
    """No usable review target could be derived; message says why."""


def detect_ci_target(env: dict[str, str] | None = None) -> str:
    """The PR/MR URL this CI run is about, from predefined variables.

    GitLab CI: merge-request pipelines carry CI_MERGE_REQUEST_IID; the MR
    URL is built from CI_PROJECT_URL, which works on self-managed hosts
    and subgroups without any extra configuration.
    GitHub Actions: pull_request events ship the whole payload at
    GITHUB_EVENT_PATH; the target is pull_request.html_url.
    """
    e = os.environ if env is None else env

    if e.get("GITLAB_CI"):
        iid = e.get("CI_MERGE_REQUEST_IID", "").strip()
        project_url = e.get("CI_PROJECT_URL", "").rstrip("/")
        if not iid:
            raise CITargetError(
                "GitLab CI detected but this is not a merge-request pipeline "
                "(CI_MERGE_REQUEST_IID is unset) — run the review job with "
                'rules: if: $CI_PIPELINE_SOURCE == "merge_request_event"'
            )
        if not project_url:
            raise CITargetError(
                "GitLab CI merge-request pipeline without CI_PROJECT_URL — "
                "cannot build the MR URL"
            )
        return f"{project_url}/-/merge_requests/{iid}"

    if e.get("GITHUB_ACTIONS"):
        event_name = e.get("GITHUB_EVENT_NAME", "")
        if event_name not in ("pull_request", "pull_request_target"):
            raise CITargetError(
                f"GitHub Actions detected but the event is {event_name!r}, "
                "not a pull_request — trigger the review job on: pull_request"
            )
        event_path = e.get("GITHUB_EVENT_PATH", "")
        payload: dict = {}
        if event_path and Path(event_path).is_file():
            payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
        url = ((payload.get("pull_request") or {}).get("html_url") or "").strip()
        if not url:
            raise CITargetError(
                "GitHub Actions pull_request event without a readable "
                "pull_request.html_url in GITHUB_EVENT_PATH"
            )
        return url

    if e.get("SYSTEM_PULLREQUEST_PULLREQUESTID") or e.get("TF_BUILD"):
        raise CITargetError(
            "Azure Pipelines detected — Azure DevOps is a recognized forge "
            "avs does not support yet; review the checked-out range instead "
            "(avs review origin/<target-branch>...HEAD)"
        )

    raise CITargetError(
        "no supported CI environment detected (looked for GitLab CI and "
        "GitHub Actions) — pass the PR/MR URL or a git range explicitly"
    )
