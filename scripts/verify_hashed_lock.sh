#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${1:-}" != "--check" ]]; then
  echo "Usage: $0 --check" >&2
  exit 2
fi

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

python3 -m venv "$work/venv"
"$work/venv/bin/python" -m pip install --disable-pip-version-check "pip-tools==7.6.1"

CUSTOM_COMPILE_COMMAND="scripts/verify_hashed_lock.sh --check" \
  "$work/venv/bin/pip-compile" \
  --generate-hashes \
  --resolver=backtracking \
  --output-file "$work/requirements.hashed.lock" \
  requirements.lock

"$work/venv/bin/python" -m pip install \
  --disable-pip-version-check \
  --require-hashes \
  --dry-run \
  --requirement "$work/requirements.hashed.lock"

python3 - "$work/requirements.hashed.lock" <<'PY'
from pathlib import Path
import re
import sys

source = Path("requirements.lock").read_text(encoding="utf-8").splitlines()
generated = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()

pin = re.compile(r"^([A-Za-z0-9_.-]+)==([^ ;\\]+)")
def pins(lines):
    return {
        (m.group(1).lower().replace("_", "-"), m.group(2))
        for line in lines
        if (m := pin.match(line.strip()))
    }

source_pins = pins(source)
generated_pins = pins(generated)
if source_pins != generated_pins:
    print("HASH_LOCK_PIN_DRIFT_FAIL", file=sys.stderr)
    print("missing:", sorted(source_pins - generated_pins), file=sys.stderr)
    print("added:", sorted(generated_pins - source_pins), file=sys.stderr)
    raise SystemExit(1)

if "--hash=sha256:" not in "\n".join(generated):
    print("HASH_LOCK_MISSING_HASHES_FAIL", file=sys.stderr)
    raise SystemExit(1)

print("HASH_LOCK_VALIDATION_PASS")
PY
