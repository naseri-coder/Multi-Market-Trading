#!/usr/bin/env bash
# Explicit, nonproduction-only preview installation. Does NOT install or
# modify the frozen v0.3.2 runtime, Compose, production database or services.
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEST=""
ACK=0
while (($#)); do
  case "$1" in
    --destination) DEST="${2-}"; shift 2 ;;
    --ack-isolated-dev-install) ACK=1; shift ;;
    *) echo "MMT_DEV_INSTALL_REFUSED:UNKNOWN_ARGUMENT" >&2; exit 2 ;;
  esac
done
if [[ "${MMT_NONPRODUCTION:-}" != 1 || "${MMT_PRODUCTION:-}" == 1 || "$ACK" != 1 || -z "$DEST" ]]; then
  echo "MMT_DEV_INSTALL_REFUSED:NONPRODUCTION_ACK_REQUIRED" >&2; exit 2
fi
if [[ "$(id -u)" == 0 ]]; then
  echo "MMT_DEV_INSTALL_REFUSED:NONROOT_REQUIRED" >&2; exit 2
fi
# Destination must be an absolute, nonexistent path under an existing
# non-symlink parent OUTSIDE the checkout. No overwrite or in-place update.
python3 - "$ROOT" "$DEST" <<'PY'
from pathlib import Path
import sys
repo = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2])
if (not target.is_absolute() or target.exists() or target.is_symlink()
        or not target.parent.is_dir() or target.parent.is_symlink()
        or target.parent.resolve() == repo
        or repo in target.parent.resolve().parents):
    raise SystemExit("MMT_DEV_INSTALL_REFUSED:ISOLATED_NEW_DIRECTORY_REQUIRED")
PY
cd "$ROOT"
python3 scripts/a6_release_preflight.py >/dev/null
# Frozen Brooks sources are verified, never copied into the preview wheel.
(cd production_source && sha256sum -c SHA256SUMS --status)
BUILD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mmt-preview-build.XXXXXXXX")"
cleanup() { rm -rf -- "$BUILD_DIR"; }
trap cleanup EXIT
python3 scripts/a6_prepare_package.py --destination "$BUILD_DIR/package" >/dev/null
python3 -m pip wheel --disable-pip-version-check --no-deps \
  --wheel-dir "$BUILD_DIR/wheels" "$BUILD_DIR/package" >/dev/null
# Read exact, previously preflight-verified metadata. No implicit "latest" wheel.
PLATFORM_VERSION="$(python3 - "$ROOT/platform_release/pyproject.toml" <<'PYVERSION'
import sys
import tomllib
from pathlib import Path
data = tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["project"]
version = data["version"]
if data["name"] != "multi-market-trading" or version not in ("0.4.0rc1", "0.4.0"):
    raise SystemExit("MMT_DEV_INSTALL_REFUSED:INVALID_PLATFORM_VERSION")
print(version)
PYVERSION
)"
WHEEL="$BUILD_DIR/wheels/multi_market_trading-${PLATFORM_VERSION}-py3-none-any.whl"
test -f "$WHEEL"
mkdir -m 700 -- "$DEST"
python3 -m venv "$DEST/venv"
# PTB and its declared dependencies are installed as a genuine wheel extra;
# do not change the A6 frozen minimal dependency/entrypoint manifest.
"$DEST/venv/bin/python" -m pip install --disable-pip-version-check \
  "$WHEEL[telegram-admin]" >/dev/null
"$DEST/venv/bin/python" -m pip check >/dev/null
"$DEST/venv/bin/naseri-markets" --check >/dev/null
"$DEST/venv/bin/python" - "$PLATFORM_VERSION" <<'PY'
import importlib.metadata as md
import sys
from telegram.ext import Application
assert md.version("multi-market-trading") == sys.argv[1]
assert Application is not None
PY
mkdir -m 700 -- "$DEST/state"
cat > "$DEST/mmt-dev" <<'LAUNCHER'
#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/venv/bin/python" -m naseri_markets.dev_operator \
  --state-dir "$HERE/state" "$@"
LAUNCHER
chmod 700 -- "$DEST/mmt-dev"
"$DEST/mmt-dev" init --ack-nonproduction-init >/dev/null
"$DEST/mmt-dev" status
echo "MMT_DEV_INSTALL_PASS:ISOLATED_PREVIEW_ONLY"
echo "Operator entry: $DEST/mmt-dev"
