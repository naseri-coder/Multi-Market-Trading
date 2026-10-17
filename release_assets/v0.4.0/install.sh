#!/usr/bin/env bash
# NASERI MARKETS v0.4.0 local-Wheel installer. Offline and nonproduction only.
# This installer alone is NOT proof of publisher authenticity or a GitHub release.
set -Eeuo pipefail
umask 077
die() { printf 'MMT_INSTALL_REFUSED_%s\n' "$1" >&2; exit 2; }
[[ "$(id -u)" -ne 0 ]] || die ROOT_INSTALL_NOT_SUPPORTED
[[ -z "${MMT_PRODUCTION+x}" ]] || die PRODUCTION_NOT_AUTHORIZED
[[ -n "${HOME:-}" && -d "$HOME" ]] || die HOME_REQUIRED
[[ "${1:-}" == "--prefix" && -n "${2:-}" && "$#" -eq 2 ]] || die EXPLICIT_PREFIX_REQUIRED
PREFIX="$2"
[[ "$PREFIX" == /* && "$PREFIX" != "/" ]] || die ABSOLUTE_PREFIX_REQUIRED
command -v python3.12 >/dev/null || die PYTHON312_REQUIRED
command -v sha256sum >/dev/null || die SHA256SUM_REQUIRED
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
WHEEL_NAME="multi_market_trading-0.4.0-py3-none-any.whl"
[[ -f "$ROOT/$WHEEL_NAME" && ! -L "$ROOT/$WHEEL_NAME" ]] || die WHEEL_MISSING
[[ -f "$ROOT/SHA256SUMS" && ! -L "$ROOT/SHA256SUMS" ]] || die CHECKSUMS_MISSING
[[ -f "$ROOT/RELEASE_MANIFEST.json" && ! -L "$ROOT/RELEASE_MANIFEST.json" ]] || die RELEASE_MANIFEST_MISSING
[[ "$(wc -l < "$ROOT/SHA256SUMS")" -eq 1 ]] || die CHECKSUMS_FORMAT
CHECK="$(cat "$ROOT/SHA256SUMS")"
[[ "$CHECK" =~ ^[0-9a-f]{64}[\ ][\ ]multi_market_trading-0\.4\.0-py3-none-any\.whl$ ]] || die CHECKSUMS_FORMAT
(cd -- "$ROOT" && sha256sum --check --status SHA256SUMS) || die WHEEL_DIGEST_MISMATCH
python3.12 - "$ROOT/RELEASE_MANIFEST.json" "$CHECK" <<'PY' || die INVALID_RELEASE_MANIFEST
import json
import pathlib
import re
import sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = sys.argv[2].split("  ", 1)
if (type(data) is not dict
        or data.get("schema") != 1
        or data.get("version") != "0.4.0"
        or data.get("distribution") != "multi-market-trading"
        or data.get("source_commit") != "7bbb3541fb6d63f960bee9f197fe026ed6d04608"
        or data.get("release_tag") != "v0.4.0"
        or data.get("wheel_sha256") != expected[0]
        or data.get("wheel_filename") != expected[1]
        or not re.fullmatch("[0-9a-f]{64}", data.get("wheel_sha256", ""))):
    sys.exit(2)
PY
python3.12 - "$PREFIX" <<'PY' || die UNSAFE_TARGET
import os
import pathlib
import sys
p = pathlib.Path(sys.argv[1])
if not p.is_absolute() or '..' in p.parts or p == pathlib.Path('/'):
    sys.exit(2)
if p.exists() or p.is_symlink():
    sys.exit(2)
parent = p.parent
while not parent.exists():
    parent = parent.parent
if parent == pathlib.Path('/') or os.geteuid() == 0:
    sys.exit(2)
for ancestor in [parent, *list(parent.parents)]:
    if ancestor.is_symlink():
        sys.exit(2)
PY
created=0
cleanup() {
  if [[ "$created" -eq 1 && -d "$PREFIX" && ! -L "$PREFIX" ]]; then
    rm -rf -- "$PREFIX"
  fi
}
trap cleanup ERR
mkdir -p -- "$PREFIX"
created=1
python3.12 -m venv "$PREFIX/venv"
export PIP_NO_INDEX=1 PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1
"$PREFIX/venv/bin/python" -m pip install --no-index --no-deps --no-cache-dir "$ROOT/$WHEEL_NAME"
"$PREFIX/venv/bin/python" -I - <<'PY'
from importlib.metadata import distribution
dist = distribution("multi-market-trading")
assert dist.version == "0.4.0", dist.version
actual = {ep.name: ep.value for ep in dist.entry_points if ep.group == "console_scripts"}
expected = {
    "naseri-markets", "naseri-custom", "naseri-paper-demo",
    "naseri-paper-pilot", "naseri-engine-admin", "naseri-brooks-replay",
    "naseri-brooks-market", "naseri-brooks-kraken-paper",
    "naseri-brooks-paper-service",
}
assert set(actual) == expected, actual
print("MMT_LOCAL_INSTALL_NINE_CLI_METADATA_PASS")
PY
MMT_NONPRODUCTION=1 APP_ENV=test "$PREFIX/venv/bin/naseri-markets" --check
"$PREFIX/venv/bin/naseri-paper-demo" --help >/dev/null
created=0
trap - ERR
printf 'MMT_OFFLINE_INSTALL_SUCCESS prefix=%s\n' "$PREFIX"
printf 'NO_LIVE_TRADES_NO_TELEGRAM_SEND_NO_PUBLISHER_SIGNATURE_VERIFIED\n'
