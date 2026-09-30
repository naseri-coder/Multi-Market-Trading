"""Fail CI when a pull request introduces new Ruff findings.

This is a ratchet for the existing public-source lint debt. It compares Ruff diagnostics
from the pull-request head against the exact base commit using the head revision's Ruff
configuration. Existing findings may remain temporarily, but new findings are rejected.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

LINT_SCOPES = ("production_source", "production_checks", "scripts")
CONTEXT_RADIUS = 2


def _run(
    command: list[str],
    *,
    cwd: Path,
    allowed_returncodes: set[int],
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in allowed_returncodes:
        raise RuntimeError(
            "command failed: "
            + " ".join(command)
            + f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _extract_base(repo_root: Path, base_sha: str, destination: Path) -> None:
    result = subprocess.run(
        ["git", "archive", "--format=tar", base_sha],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"git archive failed for {base_sha}: {stderr}")

    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        archive.extractall(destination, filter="data")


def _ruff_findings(tree: Path, config: Path) -> list[dict[str, Any]]:
    scopes = [scope for scope in LINT_SCOPES if (tree / scope).exists()]
    if not scopes:
        raise RuntimeError("no configured Ruff lint scopes exist")

    result = _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--output-format=json",
            "--config",
            str(config),
            *scopes,
        ],
        cwd=tree,
        allowed_returncodes={0, 1},
    )
    try:
        findings = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ruff did not return valid JSON") from exc

    if not isinstance(findings, list):
        raise RuntimeError("unexpected Ruff JSON result")
    return findings


def _relative_path(filename: str, tree: Path) -> str:
    path = Path(filename)
    if path.is_absolute():
        try:
            path = path.resolve().relative_to(tree.resolve())
        except ValueError as exc:
            raise RuntimeError(f"Ruff finding is outside lint tree: {filename}") from exc
    return path.as_posix()


def _source_context(tree: Path, relative_path: str, row: int) -> tuple[str, ...]:
    source = tree / relative_path
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"cannot read Ruff source file: {relative_path}") from exc

    index = max(row - 1, 0)
    start = max(index - CONTEXT_RADIUS, 0)
    end = min(index + CONTEXT_RADIUS + 1, len(lines))
    return tuple(lines[start:end])


def _fingerprint(
    finding: dict[str, Any],
    *,
    tree: Path,
) -> tuple[str, str, str, tuple[str, ...]]:
    relative_path = _relative_path(str(finding["filename"]), tree)
    location = finding.get("location") or {}
    row = int(location.get("row", 1))
    return (
        relative_path,
        str(finding.get("code") or ""),
        str(finding.get("message") or ""),
        _source_context(tree, relative_path, row),
    )


def _counter(
    findings: list[dict[str, Any]],
    *,
    tree: Path,
) -> Counter[tuple[str, str, str, tuple[str, ...]]]:
    return Counter(_fingerprint(finding, tree=tree) for finding in findings)


def _new_finding_details(
    findings: list[dict[str, Any]],
    *,
    tree: Path,
    new_counts: Counter[tuple[str, str, str, tuple[str, ...]]],
) -> list[str]:
    remaining = new_counts.copy()
    details: list[str] = []
    for finding in findings:
        fingerprint = _fingerprint(finding, tree=tree)
        if remaining[fingerprint] <= 0:
            continue
        relative_path = _relative_path(str(finding["filename"]), tree)
        location = finding.get("location") or {}
        row = int(location.get("row", 1))
        column = int(location.get("column", 1))
        code = str(finding.get("code") or "UNKNOWN")
        message = str(finding.get("message") or "")
        details.append(f"{relative_path}:{row}:{column}: {code} {message}")
        remaining[fingerprint] -= 1
    return details


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reject new Ruff findings relative to an exact Git base commit."
    )
    parser.add_argument("--base-sha", required=True)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    config = repo_root / "pyproject.toml"
    if not config.is_file():
        raise RuntimeError("pyproject.toml is missing")

    version = _run(
        [sys.executable, "-m", "ruff", "--version"],
        cwd=repo_root,
        allowed_returncodes={0},
    ).stdout.strip()

    head_findings = _ruff_findings(repo_root, config)
    with tempfile.TemporaryDirectory(prefix="ruff-base-") as temporary:
        base_root = Path(temporary)
        _extract_base(repo_root, args.base_sha, base_root)
        base_findings = _ruff_findings(base_root, config)
        base_counts = _counter(base_findings, tree=base_root)

    head_counts = _counter(head_findings, tree=repo_root)
    new_counts = head_counts - base_counts
    new_count = sum(new_counts.values())

    print(f"RUFF_VERSION={version}")
    print(f"RUFF_BASE_FINDINGS={len(base_findings)}")
    print(f"RUFF_HEAD_FINDINGS={len(head_findings)}")
    print(f"RUFF_NEW_FINDINGS={new_count}")

    if new_count:
        details = _new_finding_details(
            head_findings,
            tree=repo_root,
            new_counts=new_counts,
        )
        for detail in details[:100]:
            print(f"RUFF_NEW: {detail}")
        if len(details) > 100:
            print(f"RUFF_NEW_TRUNCATED={len(details) - 100}")
        return 1

    print("RUFF_NO_NEW_FINDINGS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
