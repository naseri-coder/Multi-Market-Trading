#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${1:-}" != "--check" ]]; then
  echo "Usage: $0 --check [--output PATH]" >&2
  exit 2
fi

[[ -s requirements.hashed.lock ]] || {
  echo "HASH_LOCK_COMMITTED_FILE_MISSING_FAIL" >&2
  exit 1
}

output=""
case "${2:-}" in
  "")
    ;;
  --output)
    [[ -n "${3:-}" ]] || { echo "--output requires a path" >&2; exit 2; }
    [[ -z "${4:-}" ]] || { echo "Usage: $0 --check [--output PATH]" >&2; exit 2; }
    output="$3"
    ;;
  *)
    echo "Usage: $0 --check [--output PATH]" >&2
    exit 2
    ;;
esac

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

if ! cmp -s requirements.hashed.lock "$work/requirements.hashed.lock"; then
  echo "HASH_LOCK_STALE_FAIL: committed requirements.hashed.lock differs from regenerated lock" >&2
  diff -u requirements.hashed.lock "$work/requirements.hashed.lock" >&2 || true
  exit 1
fi

echo "HASH_LOCK_COMMITTED_MATCH_PASS"

if [[ -n "$output" ]]; then
  install -m 0644 "$work/requirements.hashed.lock" "$output"
  echo "HASH_LOCK_ARTIFACT_READY: $output"
fi
