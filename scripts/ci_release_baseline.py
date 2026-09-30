#!/usr/bin/env python3
"""Verify or restore the published v0.2.0 release baseline without printing credentials."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

TAG = "v0.2.0"
EXPECTED_SHA = "d5abb04917c774b87f366d369da6221002ae35d8"
EXPECTED_MANIFEST_SHA = "769aa1757120c71ddf17579f18f1b63cd5ef3685a25287bd68d7c9bc7c341b49"


def api(repo: str, path: str, token: str | None, method: str = "GET", payload: dict | None = None):
    url = f"https://api.github.com/repos/{repo}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "crypto-price-action-release-baseline-guard",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()

    repo = os.environ.get("GITHUB_REPOSITORY", "naseri-coder/crypto-price-action")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    ref = api(repo, f"/git/ref/tags/{TAG}", token)
    actual = None if ref is None else ref.get("object", {}).get("sha")
    ref_type = None if ref is None else ref.get("object", {}).get("type")

    if (actual != EXPECTED_SHA or ref_type != "commit") and args.repair:
        if not token:
            print("RELEASE_BASELINE_REPAIR_FAIL: authenticated token is required", file=sys.stderr)
            return 1
        if ref is None:
            api(repo, "/git/refs", token, "POST", {"ref": f"refs/tags/{TAG}", "sha": EXPECTED_SHA})
            print("RELEASE_BASELINE_TAG_RECREATED")
        else:
            api(
                repo,
                f"/git/refs/tags/{TAG}",
                token,
                "PATCH",
                {"sha": EXPECTED_SHA, "force": True},
            )
            print("RELEASE_BASELINE_TAG_RESTORED")
        ref = api(repo, f"/git/ref/tags/{TAG}", token)
        actual = None if ref is None else ref.get("object", {}).get("sha")
        ref_type = None if ref is None else ref.get("object", {}).get("type")

    if actual != EXPECTED_SHA or ref_type != "commit":
        print(
            f"RELEASE_BASELINE_TAG_FAIL: expected {EXPECTED_SHA}, got {actual or 'missing'}",
            file=sys.stderr,
        )
        return 1

    release = api(repo, f"/releases/tags/{TAG}", token)
    if release is None:
        print("RELEASE_BASELINE_RELEASE_FAIL: release is missing", file=sys.stderr)
        return 1
    if release.get("draft") is not False or release.get("prerelease") is not True:
        print("RELEASE_BASELINE_RELEASE_STATE_FAIL", file=sys.stderr)
        return 1
    if release.get("name") != TAG or release.get("tag_name") != TAG:
        print("RELEASE_BASELINE_RELEASE_NAME_FAIL", file=sys.stderr)
        return 1

    body = release.get("body") or ""
    required_markers = (EXPECTED_SHA, EXPECTED_MANIFEST_SHA)
    if not all(marker in body for marker in required_markers):
        print("RELEASE_BASELINE_RELEASE_NOTES_FAIL", file=sys.stderr)
        return 1

    print(f"RELEASE_BASELINE_PASS tag={TAG} sha={EXPECTED_SHA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
