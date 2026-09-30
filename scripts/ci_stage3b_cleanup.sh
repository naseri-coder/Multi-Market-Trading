#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname -- "${BASH_SOURCE[0]}")/.."
[[ "${GITHUB_ACTIONS:-}" == "true" ]] || { echo "RUNNER_ONLY"; exit 3; }
[[ "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ && "${GITHUB_RUN_ATTEMPT:-}" =~ ^[0-9]+$ ]] || exit 3
[[ "${TEST_PROJECT:-}" == "stage3b-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}" ]] || exit 3
status=0
if [[ -f .env && ! -L .env ]]; then
  docker compose -p "$TEST_PROJECT" -f compose.yaml --env-file .env down --volumes --remove-orphans || status=1
fi
rm -f -- .env
if [[ "$status" -ne 0 ]]; then echo "STAGE3B_CLEANUP_FAILED"; exit 1; fi
echo "STAGE3B_OWNED_RESOURCE_CLEANUP_PASS"
