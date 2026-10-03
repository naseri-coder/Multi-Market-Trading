#!/usr/bin/env python3
"""Create a private fresh-host .env without printing generated secrets."""

import os
import re
import secrets
import sys
from pathlib import Path

target = Path(sys.argv[1] if len(sys.argv) > 1 else ".env")
example = Path(sys.argv[2] if len(sys.argv) > 2 else ".env.example")

if target.exists() or target.is_symlink():
    raise SystemExit("ENV_BOOTSTRAP_REFUSED: .env already exists")
if not example.is_file() or example.is_symlink():
    raise SystemExit("ENV_BOOTSTRAP_REFUSED: .env.example missing/invalid")
if not sys.stdin.isatty():
    raise SystemExit("ENV_BOOTSTRAP_REFUSED: interactive terminal required")

template = example.read_text(encoding="utf-8")
if template.count("REPLACE_WITH_NUMERIC_ADMIN_ID") != 1:
    raise SystemExit("ENV_BOOTSTRAP_REFUSED: ADMIN_IDS placeholder contract invalid")
if template.count("REPLACE_WITH_NEW_RANDOM_URLSAFE_PASSWORD") != 2:
    raise SystemExit("ENV_BOOTSTRAP_REFUSED: database password placeholder contract invalid")

admin = input("Numeric ADMIN_IDS (comma-separated if multiple): ").strip()
parts = admin.split(",")
if not parts or not all(
    re.fullmatch(r"[0-9]{1,19}", item)
    and 0 < int(item) <= 2**63 - 1
    for item in parts
):
    raise SystemExit("ENV_BOOTSTRAP_REFUSED: invalid ADMIN_IDS")

password = secrets.token_urlsafe(32)
text = template.replace("REPLACE_WITH_NUMERIC_ADMIN_ID", admin)
text = text.replace("REPLACE_WITH_NEW_RANDOM_URLSAFE_PASSWORD", password)
if "REPLACE_" in text:
    raise SystemExit("ENV_BOOTSTRAP_REFUSED: unresolved placeholder")

fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    with os.fdopen(fd, "w") as stream:
        stream.write(text)
except BaseException:
    target.unlink(missing_ok=True)
    raise
print("ENV_BOOTSTRAP_PASS: private .env created; generated database password not displayed")
