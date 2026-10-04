#!/usr/bin/env bash

# Shared helpers for NASERI CODER Bot Manager.
# shellcheck shell=bash

PROJECT_NAME="crypto-price-action"
PROJECT_URL="https://github.com/naseri-coder/crypto-price-action"
OFFICIAL_HTTPS_REMOTE="https://github.com/naseri-coder/crypto-price-action.git"
OFFICIAL_SSH_REMOTE="git@github.com:naseri-coder/crypto-price-action.git"
BACKUP_ROOT="${ROOT}/.naseri-backups"
LOCK_DIR="${TMPDIR:-/tmp}/naseri-${PROJECT_NAME}-${UID}.lock"

# Terminal UI v2: color is enabled only for an interactive terminal and can be
# disabled explicitly with NO_COLOR=1. Unicode decorations have an ASCII
# fallback for minimal shells and redirected output.
UI_COLOR=0
if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-dumb}" != "dumb" ]]; then
  UI_COLOR=1
fi

UI_UNICODE=0
case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
  *UTF-8*|*utf8*|*UTF8*) UI_UNICODE=1 ;;
esac

if [[ "$UI_COLOR" == "1" ]]; then
  c_reset=$'\033[0m'
  c_bold=$'\033[1m'
  c_dim=$'\033[2m'
  c_green=$'\033[32m'
  c_yellow=$'\033[33m'
  c_red=$'\033[31m'
  c_cyan=$'\033[36m'
  c_white=$'\033[97m'
else
  c_reset=""
  c_bold=""
  c_dim=""
  c_green=""
  c_yellow=""
  c_red=""
  c_cyan=""
  c_white=""
fi

if [[ "$UI_UNICODE" == "1" ]]; then
  ui_mark_ok="✓"
  ui_mark_warn="!"
  ui_mark_fail="✗"
  ui_mark_info="●"
  ui_mark_off="○"
  ui_arrow="›"
  ui_rule_char="─"
else
  ui_mark_ok="+"
  ui_mark_warn="!"
  ui_mark_fail="x"
  ui_mark_info="*"
  ui_mark_off="o"
  ui_arrow=">"
  ui_rule_char="-"
fi

say() { printf '%s\n' "$*"; }
info() { printf '%s%s INFO%s  %s\n' "$c_cyan" "$ui_mark_info" "$c_reset" "$*"; }
ok() { printf '%s%s PASS%s  %s\n' "$c_green" "$ui_mark_ok" "$c_reset" "$*"; }
warn() { printf '%s%s WARN%s  %s\n' "$c_yellow" "$ui_mark_warn" "$c_reset" "$*"; }
fail() { printf '%s%s FAIL%s  %s\n' "$c_red" "$ui_mark_fail" "$c_reset" "$*" >&2; }
die() { fail "$*"; return 1; }

is_tty() { [[ -t 0 && -t 1 ]]; }

terminal_width() {
  local cols
  cols="$(tput cols 2>/dev/null || true)"
  [[ "$cols" =~ ^[0-9]+$ ]] || cols=68
  (( cols < 60 )) && cols=60
  (( cols > 78 )) && cols=78
  printf '%s' "$cols"
}

ui_rule() {
  local width line
  width="$(terminal_width)"
  printf -v line '%*s' "$width" ''
  line="${line// /$ui_rule_char}"
  printf '%s%s%s\n' "$c_dim" "$line" "$c_reset"
}

ui_section() {
  printf '\n%s%s%s\n' "$c_bold$c_cyan" "$1" "$c_reset"
}

ui_section_danger() {
  printf '\n%s%s%s\n' "$c_bold$c_red" "$1" "$c_reset"
}

ui_kv() {
  local label="$1" value="$2"
  printf '  %-24s %s\n' "$label" "$value"
}

ui_render_state() {
  local value="$1" normalized
  normalized="${value^^}"
  case "$normalized" in
    RUNNING|READY|PRESENT|PASS|PASSED|SUCCESS|CURRENT|HEALTHY|ENABLED|VALID)
      printf '%s%s %s%s' "$c_green" "$ui_mark_info" "$normalized" "$c_reset"
      ;;
    STOPPED|DISABLED|ABSENT|NOT_INSTALLED|PENDING|CONFIGURED_NOT_INSTALLED)
      printf '%s%s %s%s' "$c_yellow" "$ui_mark_off" "$normalized" "$c_reset"
      ;;
    FAILED|FAIL|ERROR|UNAVAILABLE|CONFIGURED_DOCKER_UNAVAILABLE|INVALID)
      printf '%s%s %s%s' "$c_red" "$ui_mark_fail" "$normalized" "$c_reset"
      ;;
    *)
      printf '%s%s%s' "$c_cyan" "$value" "$c_reset"
      ;;
  esac
}

ui_state_line() {
  local label="$1" state="$2"
  printf '  %-24s ' "$label"
  ui_render_state "$state"
  printf '\n'
}

ui_bool_state() {
  case "$1" in
    true) printf 'ENABLED' ;;
    false) printf 'DISABLED' ;;
    *) printf '%s' "$1" ;;
  esac
}

ui_step() {
  local current="$1" total="$2" label="$3"
  printf '%s[%s/%s]%s %s...\n' "$c_cyan" "$current" "$total" "$c_reset" "$label"
}

ui_step_done() {
  printf '%s%s%s %s\n' "$c_green" "$ui_mark_ok" "$c_reset" "$1"
}

ui_notice() {
  local level="$1" message="$2"
  ui_rule
  case "$level" in
    DANGER) printf '%s%s%s\n' "$c_bold$c_red" "$message" "$c_reset" ;;
    WARNING) printf '%s%s%s\n' "$c_bold$c_yellow" "$message" "$c_reset" ;;
    *) printf '%s%s%s\n' "$c_bold$c_cyan" "$message" "$c_reset" ;;
  esac
  ui_rule
}

ui_prompt() {
  printf '%s%s%s ' "$c_bold$c_cyan" "$ui_arrow" "$c_reset"
}

pause_screen() {
  is_tty || return 0
  printf '\n%sPress Enter to continue...%s' "$c_dim" "$c_reset"
  read -r _
}

confirm_phrase() {
  local prompt="$1" expected="$2" answer
  is_tty || { fail "Interactive confirmation required."; return 1; }
  ui_notice "WARNING" "$prompt"
  printf 'Type %s%s%s to continue: ' "$c_bold" "$expected" "$c_reset"
  read -r answer
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

  if is_tty && command -v clear >/dev/null 2>&1; then
    clear
  fi

  if [[ "$UI_UNICODE" == "1" ]]; then
    printf '%s%s╔══════════════════════════════════════════════════════════════╗%s\n' "$c_bold" "$c_cyan" "$c_reset"
    printf '%s%s║                        NASERI CODER                          ║%s\n' "$c_bold" "$c_white" "$c_reset"
    printf '%s%s║              Crypto Price Action Manager                    ║%s\n' "$c_bold" "$c_cyan" "$c_reset"
    printf '%s%s╚══════════════════════════════════════════════════════════════╝%s\n' "$c_bold" "$c_cyan" "$c_reset"
  else
    printf '%s%s+--------------------------------------------------------------+%s\n' "$c_bold" "$c_cyan" "$c_reset"
    printf '%s%s|                        NASERI CODER                          |%s\n' "$c_bold" "$c_white" "$c_reset"
    printf '%s%s|              Crypto Price Action Manager                    |%s\n' "$c_bold" "$c_cyan" "$c_reset"
    printf '%s%s+--------------------------------------------------------------+%s\n' "$c_bold" "$c_cyan" "$c_reset"
  fi

  printf '\n'
  ui_kv "Repository" "$PROJECT_URL"
  ui_kv "Version" "${version:-unknown}"
  ui_kv "Branch" "$branch @ $sha"
  printf '  %-24s ' "State"
  ui_render_state "$state"
  printf '\n'
  ui_rule
}

safe_config_summary() {
  env_file_valid_shape || { warn "No .env file is present."; return 0; }

  ui_section "CONFIGURATION"
  printf '  %sSecret values are never displayed.%s\n' "$c_dim" "$c_reset"
  ui_kv "APP_ENV" "$(env_value APP_ENV)"
  ui_state_line "Telegram runtime" "$(ui_bool_state "$(env_value TELEGRAM_RUNTIME_ENABLED)")"
  ui_state_line "Brooks runtime" "$(ui_bool_state "$(env_value BROOKS_RUNTIME_ENABLED)")"
  ui_kv "Brooks mode" "$(env_value BROOKS_RUNTIME_MODE)"
  ui_state_line "Brooks operations" "$(ui_bool_state "$(env_value BROOKS_OPERATIONS_ENABLED)")"
  ui_state_line "Paper runtime" "$(ui_bool_state "$(env_value PAPER_RUNTIME_ENABLED)")"
  ui_state_line "Performance reports" "$(ui_bool_state "$(env_value PERFORMANCE_REPORTS_ENABLED)")"
  ui_kv "Exchange / market" "$(env_value BROOKS_EXCHANGE) / $(env_value BROOKS_MARKET_TYPE)"
  ui_kv "Symbols" "$(env_value BROOKS_SYMBOLS)"
  ui_kv "Timeframes" "$(env_value BROOKS_TIMEFRAMES)"
  ui_kv "Scale-in" "$(env_value BROOKS_SCALE_IN_MODE)"
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
    compose run --rm --no-deps bot \
      python release_tools/validate_release_config.py --from-environment --mode "$mode"
    return $?
  fi

  if PYTHONPATH="$ROOT/production_source" python3 -c 'import pydantic_settings' >/dev/null 2>&1; then
    PYTHONPATH="$ROOT/production_source" python3 "$ROOT/scripts/validate_release_config.py" \
      --env-file "$ROOT/.env" --mode "$mode"
    return $?
  fi

  if [[ "$mode" == "safe-install" ]]; then
    ok "Host preflight passed; typed application validation will run after the image is built."
    return 0
  fi
  fail "Typed validation for active runtime requires the project image or Python dependencies."
  return 1
}
