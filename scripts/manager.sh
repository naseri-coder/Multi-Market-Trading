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

manager_help() {
  cat <<'HELP'
NASERI CODER — Crypto Price Action Bot Manager

Usage:
  bash scripts/manager.sh
  bash scripts/manager.sh <command>

Commands:
  install       Fresh-host installation using the existing fail-closed installer
  update        Safe fast-forward update with mandatory backup
  start         Start PostgreSQL and bot after validation
  stop          Stop bot (keep PostgreSQL)
  restart       Validate and restart bot
  status        Show installation/runtime status
  logs          Follow bot logs
  config        Open configuration menu
  doctor        Run diagnostics
  verify        Verify repository and installed runtime
  env-check     Run environment preflight
  database      Open database management menu
  backup        Create a full backup
  backups       Open backup menu
  restore       Open restore menu
  repair        Open repair/diagnose menu
  system        Show system information
  uninstall     Open guarded runtime removal menu
  menu          Open interactive menu
  --self-test   Offline manager static self-test
  --help        Show this help
HELP
}

manager_self_test() {
  local required path
  for required in     naseri.sh     scripts/install.sh     scripts/manager.sh     scripts/lib/manager_common.sh     scripts/lib/manager_backup.sh     scripts/lib/manager_runtime.sh     scripts/check_env.py     scripts/verify.sh     compose.yaml     pyproject.toml; do
    [[ -s "$ROOT/$required" ]] || {
      printf 'MANAGER_SELF_TEST_FAIL missing=%s\n' "$required" >&2
      return 1
    }
  done

  for path in     "$ROOT/naseri.sh"     "$ROOT/scripts/install.sh"     "$ROOT/scripts/manager.sh"     "$ROOT/scripts/lib/manager_common.sh"     "$ROOT/scripts/lib/manager_backup.sh"     "$ROOT/scripts/lib/manager_runtime.sh"; do
    bash -n "$path"
  done

  [[ "$PROJECT_URL" == "https://github.com/naseri-coder/crypto-price-action" ]]
  [[ "$OFFICIAL_HTTPS_REMOTE" == "${PROJECT_URL}.git" ]]
  [[ -n "$(project_version)" ]]
  grep -Fq 'python -m alembic -c alembic.ini upgrade head' "$ROOT/scripts/install.sh"
  grep -Fq 'merge --ff-only' "$ROOT/scripts/lib/manager_runtime.sh"
  grep -Fq 'DELETE-RUNTIME-DATA' "$ROOT/scripts/lib/manager_runtime.sh"
  grep -Fq 'pg_dump' "$ROOT/scripts/lib/manager_backup.sh"
  grep -Fq 'pg_restore' "$ROOT/scripts/lib/manager_backup.sh"
  grep -Fq 'Environment Check' "$ROOT/scripts/manager.sh"
  grep -Fq 'Database Management' "$ROOT/scripts/manager.sh"
  grep -Fq 'Repair / Diagnose' "$ROOT/scripts/manager.sh"
  grep -Fq 'Uninstall / Remove Runtime' "$ROOT/scripts/manager.sh"
  grep -Fq 'NO_COLOR' "$ROOT/scripts/lib/manager_common.sh"
  grep -Fq 'ui_step' "$ROOT/scripts/lib/manager_common.sh"
  printf 'MANAGER_SELF_TEST_PASS version=%s\n' "$(project_version)"
}

main_menu() {
  local choice
  while true; do
    banner

    ui_section "INSTALLATION"
    printf '  %s[1]%s  Install Bot\n' "$c_bold" "$c_reset"
    printf '  %s[2]%s  Update Bot\n' "$c_bold" "$c_reset"

    ui_section "RUNTIME"
    printf '  %s[3]%s  Start Bot\n' "$c_bold" "$c_reset"
    printf '  %s[4]%s  Stop Bot\n' "$c_bold" "$c_reset"
    printf '  %s[5]%s  Restart Bot\n' "$c_bold" "$c_reset"
    printf '  %s[6]%s  Bot Status\n' "$c_bold" "$c_reset"
    printf '  %s[7]%s  View Logs\n' "$c_bold" "$c_reset"

    ui_section "SYSTEM"
    printf '  %s[8]%s  Configuration\n' "$c_bold" "$c_reset"
    printf '  %s[9]%s  Environment Check\n' "$c_bold" "$c_reset"
    printf '  %s[10]%s Database Management\n' "$c_bold" "$c_reset"

    ui_section "DATA"
    printf '  %s[11]%s Backup\n' "$c_bold" "$c_reset"
    printf '  %s[12]%s Restore\n' "$c_bold" "$c_reset"

    ui_section "MAINTENANCE"
    printf '  %s[13]%s Repair / Diagnose\n' "$c_bold" "$c_reset"
    printf '  %s[14]%s Verify Installation\n' "$c_bold" "$c_reset"
    printf '  %s[15]%s System Information\n' "$c_bold" "$c_reset"

    ui_section_danger "DANGER ZONE"
    printf '  %s[16]%s Uninstall / Remove Runtime\n' "$c_red$c_bold" "$c_reset"

    printf '\n  %s[0]%s  Exit\n' "$c_dim" "$c_reset"
    ui_rule
    ui_prompt
    printf 'Select an option: '
    read -r choice

    case "$choice" in
      1) run_locked install_bot; pause_screen ;;
      2) run_locked update_bot; pause_screen ;;
      3) run_locked start_bot; pause_screen ;;
      4) run_locked stop_bot; pause_screen ;;
      5) run_locked restart_bot; pause_screen ;;
      6) show_status; pause_screen ;;
      7) view_logs; pause_screen ;;
      8) configuration_menu ;;
      9) environment_check; pause_screen ;;
      10) database_menu ;;
      11) backup_create_menu ;;
      12) restore_menu ;;
      13) repair_menu ;;
      14) run_locked verify_installation; pause_screen ;;
      15) system_information; pause_screen ;;
      16) run_locked uninstall_bot; pause_screen ;;
      0) say "Goodbye."; return 0 ;;
      *) warn "Invalid selection."; pause_screen ;;
    esac
  done
}

dispatch() {
  local command="${1:-menu}"
  case "$command" in
    menu) main_menu ;;
    install) run_locked install_bot ;;
    update) run_locked update_bot ;;
    start) run_locked start_bot ;;
    stop) run_locked stop_bot ;;
    restart) run_locked restart_bot ;;
    status) show_status ;;
    logs) view_logs ;;
    config) configuration_menu ;;
    env-check) environment_check ;;
    database) database_menu ;;
    doctor) doctor ;;
    verify) run_locked verify_installation ;;
    backup) run_locked create_backup "manual" "full" ;;
    backups) backup_create_menu ;;
    restore) restore_menu ;;
    repair) repair_menu ;;
    system) system_information ;;
    uninstall) run_locked uninstall_bot ;;
    --self-test) manager_self_test ;;
    --help|-h|help) manager_help ;;
    *)
      fail "Unknown manager command: $command"
      manager_help >&2
      return 2
      ;;
  esac
}

dispatch "$@"
