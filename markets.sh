#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Public, canonical-brand launcher. The v0.3.2 runtime identifiers remain
# intentionally unchanged until a separate release migration is approved.
exec bash "$ROOT/scripts/manager.sh" "$@"
