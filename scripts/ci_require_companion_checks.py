#!/usr/bin/env python3
"""Require companion PR checks before the protected publication gate may pass."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

REQUIRED = (
    ("public-tests", "github-actions"),
    ("CodeQL", "github-advanced-security"),
)
POLL_SECONDS = 10
TIMEOUT_SECONDS = 600


def fetch_checks(repo: str, sha: str, token: str) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs?per_page=100"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "crypto-price-action-companion-check-gate",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response).get("check_runs", [])


def latest_matching(checks: list[dict], name: str, app_slug: str) -> dict | None:
    matches = [
        check
        for check in checks
        if check.get("name") == name and check.get("app", {}).get("slug") == app_slug
    ]
    return max(matches, key=lambda item: int(item.get("id", 0)), default=None)


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY")
    sha = os.environ.get("CHECK_SHA")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not repo or not sha or not token:
        print("COMPANION_CHECK_INPUT_FAIL", file=sys.stderr)
        return 1

    deadline = time.monotonic() + TIMEOUT_SECONDS
    while True:
        checks = fetch_checks(repo, sha, token)
        pending: list[str] = []
        for name, app_slug in REQUIRED:
            check = latest_matching(checks, name, app_slug)
            if check is None:
                pending.append(f"{name}:missing")
                continue
            status = check.get("status")
            conclusion = check.get("conclusion")
            if status != "completed":
                pending.append(f"{name}:{status or 'unknown'}")
                continue
            if conclusion != "success":
                print(
                    f"COMPANION_CHECK_FAIL name={name} app={app_slug} conclusion={conclusion}",
                    file=sys.stderr,
                )
                return 1

        if not pending:
            print("COMPANION_CHECKS_PASS public-tests=success CodeQL=success")
            return 0

        if time.monotonic() >= deadline:
            print("COMPANION_CHECK_TIMEOUT " + ",".join(pending), file=sys.stderr)
            return 1

        print("COMPANION_CHECK_WAIT " + ",".join(pending))
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
