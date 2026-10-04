#!/usr/bin/env bash

# Shared helpers for NASERI CODER Bot Manager.
# shellcheck shell=bash

PROJECT_NAME="crypto-price-action"
PROJECT_URL="https://github.com/naseri-coder/crypto-price-action"
OFFICIAL_HTTPS_REMOTE="https://github.com/naseri-coder/crypto-price-action.git"
OFFICIAL_SSH_REMOTE="git@github.com:naseri-coder/crypto-price-action.git"
BACKUP_ROOT="${ROOT}/.naseri-backups"
LOCK_DIR="${TMPDIR:-/tmp}/naseri-${PROJECT_NAME}-${UID}.lock"

c_reset=$'\033[0m'
c_bold=$'\033[1m'
c_green=$'\033[32m'
c_yellow=$'\033[33m'
c_red=$'\033[31m'
c_cyan=$'\033[36m'

say() { printf '%s\n' "$*"; }
info() { printf '%s[INFO]%s %s\n' "$c_cyan" "$c_reset" "$*"; }
ok() { printf '%s[PASS]%s %s\n' "$c_green" "$c_reset" "$*"; }
warn() { printf '%s[WARN]%s %s\n' "$c_yellow" "$c_reset" "$*"; }
fail() { printf '%s[FAIL]%s %s\n' "$c_red" "$c_reset" "$*" >&2; }
die() { fail "$*"; return 1; }

is_tty() { [[ -t 0 && -t 1 ]]; }

pause_screen() {
  is_tty || return 0
  printf '\nPress Enter to continue...'
  read -r _
}

confirm_phrase() {
  local prompt="$1" expected="$2" answer
  is_tty || { fail "Interactive confirmation required."; return 1; }
  printf '%s\n' "$prompt"
  read -r -p "Type ${expected} to continue: " answer
  [[ "$answer" == "$expected" ]] || { warn "Cancelled."; return 1; }
}

command_exists() { command -v "$1" >/dev/null 2>&1; }

require_command() {
  command_exists "$1" || { fail "Missing prerequisite: $1"; return 1; }
}

project_version() {
  awk -F'"' '/^version = "/ {print $2; exit}' "$ROOT/pyproject.toml" 2>/dev/null || true
}

git_branch() {
  git -C "$ROOT" symbolic-ref --quiet --short HEAD 2>/dev/null || printf '%s' "detached"
}

git_short_sha() {
  git -C "$ROOT" rev-parse --short=12 HEAD 2>/dev/null || printf '%s' "unknown"
}

repo_is_git_checkout() {
  git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

official_remote_ok() {
  local remote
  remote="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
  [[ "$remote" == "$OFFICIAL_HTTPS_REMOTE" || "$remote" == "$OFFICIAL_SSH_REMOTE" ]]
}

env_file_valid_shape() {
  [[ -f "$ROOT/.env" && ! -L "$ROOT/.env" ]]
}

env_value() {
  local key="$1"
  case "$key" in
    APP_ENV|LOG_LEVEL|LOG_FORMAT|TELEGRAM_RUNTIME_ENABLED|BROOKS_RUNTIME_ENABLED|BROOKS_OPERATIONS_ENABLED|PAPER_RUNTIME_ENABLED|PERFORMANCE_REPORTS_ENABLED|BROOKS_RUNTIME_MODE|BROOKS_EXCHANGE|BROOKS_MARKET_TYPE|BROOKS_SYMBOLS|BROOKS_TIMEFRAMES|BROOKS_SCALE_IN_MODE)
      ;;
    *)
      fail "Refused to read non-display configuration key: $key"
      return 1
      ;;
  esac
  awk -F= -v wanted="$key" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "$ROOT/.env" 2>/dev/null
}

compose() {
  docker compose -p "$PROJECT_NAME" -f "$ROOT/compose.yaml" --env-file "$ROOT/.env" "$@"
}

docker_ready() {
  command_exists docker &&
    docker compose version >/dev/null 2>&1 &&
    docker info >/dev/null 2>&1
}

volume_exists() {
  docker volume inspect "${PROJECT_NAME}_postgres_data" >/dev/null 2>&1
}

service_running() {
  local service="$1" cid
  env_file_valid_shape || return 1
  docker_ready || return 1
  cid="$(compose ps -q "$service" 2>/dev/null || true)"
  [[ -n "$cid" ]] || return 1
  [[ "$(docker inspect --format '{{.State.Running}}' "$cid" 2>/dev/null || true)" == "true" ]]
}

bot_running() { service_running bot; }
postgres_running() { service_running postgres; }

installation_state() {
  if ! env_file_valid_shape; then
    printf '%s' "NOT_INSTALLED"
  elif ! docker_ready; then
    printf '%s' "CONFIGURED_DOCKER_UNAVAILABLE"
  elif bot_running; then
    printf '%s' "RUNNING"
  elif volume_exists; then
    printf '%s' "INSTALLED_STOPPED"
  else
    printf '%s' "CONFIGURED_NOT_INSTALLED"
  fi
}

assert_no_inherited_db_overrides() {
  local name
  for name in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL; do
    if [[ -v "$name" ]]; then
      fail "Inherited database override detected for $name (value suppressed)."
      return 1
    fi
  done
}

check_compose_prereqs() {
  env_file_valid_shape || { fail ".env missing or unsafe (symlinks are refused)."; return 1; }
  require_command docker || return 1
  docker compose version >/dev/null 2>&1 || { fail "Docker Compose v2 is unavailable."; return 1; }
  docker info >/dev/null 2>&1 || { fail "Docker daemon is not reachable by this user."; return 1; }
  assert_no_inherited_db_overrides || return 1
  compose config --quiet >/dev/null || { fail "Compose configuration validation failed."; return 1; }
}

run_locked() {
  local rc
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    fail "Another NASERI CODER manager operation appears to be running."
    return 1
  fi
  set +e
  "$@"
  rc=$?
  set -e
  rmdir "$LOCK_DIR" 2>/dev/null || true
  return "$rc"
}

banner() {
  local version state branch sha
  version="$(project_version)"
  state="$(installation_state)"
  branch="$(git_branch)"
  sha="$(git_short_sha)"
  command -v clear >/dev/null 2>&1 && clear || true
  printf '%s' "$c_bold"
  cat <<'BANNER'
╔════════════════════════════════════════════════════════════╗
║                        NASERI CODER                        ║
║              Crypto Price Action Bot Manager              ║
╚════════════════════════════════════════════════════════════╝
BANNER
  printf '%s' "$c_reset"
  printf 'Project : %s\n' "$PROJECT_URL"
  printf 'Version : %s\n' "${version:-unknown}"
  printf 'Branch  : %s @ %s\n' "$branch" "$sha"
  printf 'State   : %s\n' "$state"
  printf '%s\n' '────────────────────────────────────────────────────────────'
}

safe_config_summary() {
  env_file_valid_shape || { warn "No .env file is present."; return 0; }
  say "Safe configuration summary (secret values are never displayed):"
  printf '  APP_ENV................ %s\n' "$(env_value APP_ENV)"
  printf '  Telegram runtime....... %s\n' "$(env_value TELEGRAM_RUNTIME_ENABLED)"
  printf '  Brooks runtime......... %s\n' "$(env_value BROOKS_RUNTIME_ENABLED)"
  printf '  Brooks mode............ %s\n' "$(env_value BROOKS_RUNTIME_MODE)"
  printf '  Brooks operations...... %s\n' "$(env_value BROOKS_OPERATIONS_ENABLED)"
  printf '  Paper runtime.......... %s\n' "$(env_value PAPER_RUNTIME_ENABLED)"
  printf '  Performance reports.... %s\n' "$(env_value PERFORMANCE_REPORTS_ENABLED)"
  printf '  Exchange / market...... %s / %s\n' "$(env_value BROOKS_EXCHANGE)" "$(env_value BROOKS_MARKET_TYPE)"
  printf '  Symbols................ %s\n' "$(env_value BROOKS_SYMBOLS)"
  printf '  Timeframes............. %s\n' "$(env_value BROOKS_TIMEFRAMES)"
  printf '  Scale-in............... %s\n' "$(env_value BROOKS_SCALE_IN_MODE)"
}

detect_validation_mode() {
  local telegram brooks ops paper mode
  telegram="$(env_value TELEGRAM_RUNTIME_ENABLED)"
  brooks="$(env_value BROOKS_RUNTIME_ENABLED)"
  ops="$(env_value BROOKS_OPERATIONS_ENABLED)"
  paper="$(env_value PAPER_RUNTIME_ENABLED)"
  mode="$(env_value BROOKS_RUNTIME_MODE)"
  if [[ "$telegram" == "false" && "$brooks" == "false" && "$ops" == "false" && "$paper" == "false" ]]; then
    printf '%s' "safe-install"
  elif [[ "$telegram" == "true" && "$brooks" == "true" && "$ops" == "false" && "$paper" == "true" && "$mode" == "paper" ]]; then
    printf '%s' "paper"
  elif [[ "$telegram" == "true" && "$brooks" == "true" && "$paper" == "false" && "$mode" == "live" ]]; then
    printf '%s' "live"
  else
    printf '%s' "unknown"
  fi
}

validate_current_config() {
  local mode
  env_file_valid_shape || { fail ".env missing or unsafe."; return 1; }
  mode="$(detect_validation_mode)"
  [[ "$mode" != "unknown" ]] || { fail "Configuration does not match a supported safe-install/paper/live shape."; return 1; }

  if [[ "$mode" == "safe-install" ]]; then
    python3 "$ROOT/scripts/check_env.py" "$ROOT/.env" || return 1
  fi

  if docker_ready && docker image inspect "crypto-price-action:${RELEASE_TAG:-v$(project_version)}" >/dev/null 2>&1; then
    compose run --rm --no-deps bot       python release_tools/validate_release_config.py --from-environment --mode "$mode"
    return $?
  fi

  if PYTHONPATH="$ROOT/production_source" python3 -c 'import pydantic_settings' >/dev/null 2>&1; then
    PYTHONPATH="$ROOT/production_source" python3 "$ROOT/scripts/validate_release_config.py"       --env-file "$ROOT/.env" --mode "$mode"
    return $?
  fi

  if [[ "$mode" == "safe-install" ]]; then
    ok "Host preflight passed; typed application validation will run after the image is built."
    return 0
  fi
  fail "Typed validation for active runtime requires the project image or Python dependencies."
  return 1
}
