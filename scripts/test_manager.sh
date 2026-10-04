#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/lib/manager_common.sh
source "$ROOT/scripts/lib/manager_common.sh"
# shellcheck source=scripts/lib/manager_backup.sh
source "$ROOT/scripts/lib/manager_backup.sh"
# shellcheck source=scripts/lib/manager_runtime.sh
source "$ROOT/scripts/lib/manager_runtime.sh"

fail_test() {
  printf 'MANAGER_BEHAVIOR_TEST_FAIL %s\n' "$*" >&2
  exit 1
}

assert_eq() {
  local expected="$1" actual="$2" label="$3"
  [[ "$actual" == "$expected" ]] || fail_test "$label expected=$expected actual=$actual"
}

# ---------------------------------------------------------------------------
# Installation state machine
# ---------------------------------------------------------------------------
TEST_ENV=0
TEST_DOCKER=1
TEST_VOLUME=0
TEST_BOT=0

env_file_valid_shape() { [[ "$TEST_ENV" == "1" ]]; }
docker_ready() { [[ "$TEST_DOCKER" == "1" ]]; }
volume_exists() { [[ "$TEST_VOLUME" == "1" ]]; }
bot_running() { [[ "$TEST_BOT" == "1" ]]; }
postgres_running() { return 1; }

TEST_ENV=0 TEST_DOCKER=1 TEST_VOLUME=0 TEST_BOT=0
assert_eq "NOT_INSTALLED" "$(installation_state)" "state fresh"

TEST_ENV=1 TEST_DOCKER=1 TEST_VOLUME=0 TEST_BOT=0
assert_eq "CONFIGURED_NOT_INSTALLED" "$(installation_state)" "state configured"

TEST_ENV=1 TEST_DOCKER=1 TEST_VOLUME=1 TEST_BOT=0
assert_eq "INSTALLED_STOPPED" "$(installation_state)" "state installed stopped"

TEST_ENV=1 TEST_DOCKER=1 TEST_VOLUME=1 TEST_BOT=1
assert_eq "RUNNING" "$(installation_state)" "state running"

TEST_ENV=0 TEST_DOCKER=1 TEST_VOLUME=1 TEST_BOT=0
assert_eq "RECOVERY_REQUIRED" "$(installation_state)" "state missing config with db"

TEST_ENV=1 TEST_DOCKER=0 TEST_VOLUME=0 TEST_BOT=0
assert_eq "CONFIGURED_DOCKER_UNAVAILABLE" "$(installation_state)" "state docker unavailable"

# ---------------------------------------------------------------------------
# Install routing: an installed/recovery system must never call fresh installer
# ---------------------------------------------------------------------------
INSTALL_CALLS=0
run_fresh_installer() {
  INSTALL_CALLS=$((INSTALL_CALLS + 1))
  return 0
}

installation_state() { printf '%s' "INSTALLED_STOPPED"; }
if install_bot >/dev/null 2>&1; then
  fail_test "install accepted INSTALLED_STOPPED"
fi
assert_eq "0" "$INSTALL_CALLS" "fresh installer call count installed"

installation_state() { printf '%s' "RECOVERY_REQUIRED"; }
if install_bot >/dev/null 2>&1; then
  fail_test "install accepted RECOVERY_REQUIRED"
fi
assert_eq "0" "$INSTALL_CALLS" "fresh installer call count recovery"

installation_state() { printf '%s' "NOT_INSTALLED"; }
install_bot >/dev/null
assert_eq "1" "$INSTALL_CALLS" "fresh installer call count fresh"

# ---------------------------------------------------------------------------
# Interactive failure containment: a failed menu action must not terminate menu
# ---------------------------------------------------------------------------
pause_screen() { return 0; }
failing_action() { return 7; }
menu_action failing_action >/dev/null
assert_eq "0" "$?" "menu failure containment"

# ---------------------------------------------------------------------------
# Lock fallback: stale PID lock must recover and clean itself
# ---------------------------------------------------------------------------
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
LOCK_DIR="$tmp/lockdir"
LOCK_FILE="$tmp/lockfile"
MARKER="$tmp/ran"
mkdir "$LOCK_DIR"
printf '%s\n' "99999999" > "$LOCK_DIR/owner.pid"
lock_test_action() { : > "$MARKER"; }
command_exists() {
  if [[ "$1" == "flock" ]]; then
    return 1
  fi
  command -v "$1" >/dev/null 2>&1
}
run_locked lock_test_action >/dev/null
[[ -f "$MARKER" ]] || fail_test "stale lock recovery did not run action"
[[ ! -d "$LOCK_DIR" ]] || fail_test "fallback lock directory was not cleaned"

# Restore normal command discovery for remaining checks.
command_exists() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# Backup allocation: same-second labels must still be unique
# ---------------------------------------------------------------------------
BACKUP_ROOT="$tmp/backups"
timestamp_utc() { printf '%s' "20261004T000000Z"; }
d1="$(new_backup_dir manual)"
d2="$(new_backup_dir manual)"
[[ "$d1" != "$d2" ]] || fail_test "backup directories collided"
[[ -d "$d1" && -d "$d2" ]] || fail_test "backup directories missing"

# ---------------------------------------------------------------------------
# Static safety invariants around the fixed regressions
# ---------------------------------------------------------------------------
volume_line="$(grep -n 'docker volume inspect crypto-price-action_postgres_data' scripts/install.sh | head -n1 | cut -d: -f1)"
bootstrap_line="$(grep -n 'bootstrap_env.py .env .env.example' scripts/install.sh | head -n1 | cut -d: -f1)"
[[ "$volume_line" =~ ^[0-9]+$ && "$bootstrap_line" =~ ^[0-9]+$ ]] || fail_test "installer ordering markers missing"
(( volume_line < bootstrap_line )) || fail_test "installer creates config before existing-volume refusal"

if grep -Fq '$(select_backup_dir)' scripts/lib/manager_backup.sh scripts/lib/manager_runtime.sh; then
  fail_test "restore selection still uses command substitution"
fi

if grep -Eq 'run_locked [^;]+; pause_screen' scripts/manager.sh scripts/lib/manager_runtime.sh scripts/lib/manager_backup.sh; then
  fail_test "interactive locked action can still escape menu through errexit"
fi

grep -Fq 'RECOVERY_REQUIRED' scripts/lib/manager_common.sh || fail_test "recovery state missing"
grep -Fq 'menu_locked_action install_bot' scripts/manager.sh || fail_test "main menu install action is not failure-contained"

state_render="$(ui_render_state INSTALLED_STOPPED)"
case "$state_render" in
  *INSTALLED_STOPPED*) ;;
  *) fail_test "installed-stopped state rendering missing" ;;
esac

printf 'MANAGER_BEHAVIOR_TEST_PASS\n'
