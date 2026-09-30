#!/usr/bin/env python3
"""Publication-safety checks for the tracked release tree.

This check is intentionally conservative and does not print secret-like values.
It validates path policy and scans UTF-8 text for high-confidence credential forms.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_SUFFIXES = {
    ".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3",
    ".dump", ".log", ".bak", ".tmp", ".pdf", ".doc", ".docx",
    ".xls", ".xlsx", ".zip", ".tar", ".gz",
}
FORBIDDEN_BASENAMES = {".env"}
ALLOWED_ENV = {".env.example"}

PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github-token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    "openai-key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "telegram-bot-token": re.compile(r"\b[0-9]{6,12}:[A-Za-z0-9_-]{30,}\b"),
}

def tracked_files() -> list[Path]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [ROOT / item.decode() for item in raw.split(b"\0") if item]

def main() -> None:
    failures: list[str] = []
    checked = 0
    for path in tracked_files():
        rel = path.relative_to(ROOT)
        name = path.name
        lower_parts = {part.lower() for part in rel.parts}
        if name in FORBIDDEN_BASENAMES and name not in ALLOWED_ENV:
            failures.append(f"forbidden tracked path: {rel}")
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden tracked file type: {rel}")
            continue
        if {"backups", "artifacts", "research_output"} & lower_parts:
            failures.append(f"forbidden tracked data directory: {rel}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        checked += 1
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{label} candidate in {rel} (value suppressed)")
    if failures:
        raise SystemExit("PUBLICATION_SAFETY_FAIL\n" + "\n".join(sorted(set(failures))))
    print(f"PUBLICATION_SAFETY_PASS text_files={checked}")

if __name__ == "__main__":
    main()
