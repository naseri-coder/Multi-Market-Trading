#!/usr/bin/env bash

# Runtime, update, diagnostics and uninstall workflows.
# shellcheck shell=bash

run_fresh_installer() {
  bash "$ROOT/scripts/install.sh" --install
}

install_bot() {
  local state
  state="$(installation_state)"
  case "$state" in
    RUNNING)
      warn "Bot is already installed and running. Use Update Bot for source updates."
      return 3
      ;;
    INSTALLED_STOPPED)
      warn "Bot is already installed but stopped. Use Start Bot or Update Bot; fresh install is not applicable."
      return 3
      ;;
    RECOVERY_REQUIRED)
      fail "Database volume exists but .env is missing. Fresh install is blocked to protect existing data; restore configuration or use Repair/Diagnose."
      return 3
      ;;
    CONFIGURED_DOCKER_UNAVAILABLE)
      fail "Configuration exists but Docker is unavailable. Fix Docker access before installation actions."
      return 3
      ;;
    NOT_INSTALLED|CONFIGURED_NOT_INSTALLED)
      info "Launching the fail-closed fresh-host installer."
      run_fresh_installer
      ;;
    *)
      fail "Unknown installation state: $state"
      return 3
      ;;
  esac
}

restore_previous_bot_container() {
  local was_running="$1"
  [[ "$was_running" == "1" ]] || return 0
  if compose start bot >/dev/null 2>&1; then
    warn "Previous bot container was restarted after a pre-migration failure."
  else
    fail "Could not restore the previously running bot container."
  fi
}


DB_AUTH_STATUS="UNKNOWN"

database_auth_probe() {
  local output=""
  DB_AUTH_STATUS="UNKNOWN"

  check_compose_prereqs >/dev/null 2>&1 || {
    DB_AUTH_STATUS="UNAVAILABLE"
    return 1
  }
  volume_exists || {
    DB_AUTH_STATUS="NO_VOLUME"
    return 1
  }
  postgres_running || {
    DB_AUTH_STATUS="POSTGRES_STOPPED"
    return 1
  }

  if output="$(compose exec -T postgres sh -c \
    'PGPASSWORD="$POSTGRES_PASSWORD" psql -X -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT 1"' \
    2>&1)"; then
    DB_AUTH_STATUS="READY"
    return 0
  fi

  case "$output" in
    *"password authentication failed"*)
      DB_AUTH_STATUS="PASSWORD_MISMATCH"
      ;;
    *"role "*" does not exist"*)
      DB_AUTH_STATUS="ROLE_MISMATCH"
      ;;
    *"database "*" does not exist"*)
      DB_AUTH_STATUS="DATABASE_MISMATCH"
      ;;
    *)
      DB_AUTH_STATUS="FAILED"
      ;;
  esac
  return 1
}

report_database_auth_failure() {
  case "$DB_AUTH_STATUS" in
    PASSWORD_MISMATCH)
      fail "Database password does not match the existing PostgreSQL volume."
      warn "Use Repair / Diagnose -> Repair database credentials. No database data will be deleted."
      ;;
    ROLE_MISMATCH)
      fail "Configured PostgreSQL role does not exist in the existing database volume."
      warn "Do not create a new role automatically. Restore the correct configuration from backup."
      ;;
    DATABASE_MISMATCH)
      fail "Configured PostgreSQL database does not exist in the existing volume."
      warn "Restore the correct configuration from backup before starting the bot."
      ;;
    POSTGRES_STOPPED)
      fail "PostgreSQL is not running."
      ;;
    NO_VOLUME)
      fail "Database volume does not exist."
      ;;
    UNAVAILABLE)
      fail "Database authentication check is unavailable because prerequisites are not ready."
      ;;
    *)
      fail "Database authentication/connectivity check failed."
      ;;
  esac
}

run_app_database_check() {
  local tmp rc=0
  tmp="$(mktemp "${TMPDIR:-/tmp}/naseri-db-check.XXXXXX")" || return 1
  chmod 600 "$tmp" 2>/dev/null || true

  if compose run --rm --no-deps bot python -m app --check-db >"$tmp" 2>&1; then
    rm -f -- "$tmp"
    return 0
  fi
  rc=$?

  if grep -Eqi 'InvalidPasswordError|password authentication failed' "$tmp"; then
    DB_AUTH_STATUS="PASSWORD_MISMATCH"
    report_database_auth_failure
  else
    cat "$tmp" >&2
    fail "Application database check failed."
  fi
  rm -f -- "$tmp"
  return "$rc"
}

require_database_auth() {
  if database_auth_probe; then
    return 0
  fi
  report_database_auth_failure
  return 1
}


start_bot() {
  ui_step 1 4 "Checking installation prerequisites"
  check_compose_prereqs || return 1
  volume_exists || {
    fail "No project database volume exists. Use Install Bot first."
    return 1
  }
  ui_step_done "Installation prerequisites passed"

  ui_step 2 4 "Validating configuration"
  validate_current_config || return 1
  ui_step_done "Configuration is valid"

  ui_step 3 4 "Starting PostgreSQL and checking database"
  compose up -d --wait postgres || return 1
  require_database_auth || return 1
  compose run --rm --no-deps bot python -m app --check-config || return 1
  run_app_database_check || return 1
  ui_step_done "PostgreSQL authentication and database checks passed"

  ui_step 4 4 "Starting bot"
  compose up -d --no-deps bot || return 1
  ui_step_done "Bot started"
  ok "Runtime is ready."
}

stop_bot() {
  check_compose_prereqs || return 1
  compose stop bot
  ok "Bot stopped. PostgreSQL remains available."
}

restart_bot() {
  check_compose_prereqs || return 1
  volume_exists || { fail "No installation volume exists."; return 1; }
  validate_current_config || return 1
  compose stop bot >/dev/null 2>&1 || true
  start_bot
}

show_status() {
  banner
  local version branch sha bot_state db_state volume_state docker_state install_state db_auth_state
  version="$(project_version)"
  branch="$(git_branch)"
  sha="$(git_short_sha)"
  bot_state="STOPPED"
  db_state="STOPPED"
  volume_state="ABSENT"
  docker_state="UNAVAILABLE"
  db_auth_state="NOT_CHECKED"
  install_state="$(installation_state)"

  docker_ready && docker_state="HEALTHY"
  bot_running && bot_state="RUNNING"
  postgres_running && db_state="RUNNING"
  docker_ready && volume_exists && volume_state="PRESENT"
  if [[ "$db_state" == "RUNNING" && "$volume_state" == "PRESENT" && -f "$ROOT/.env" ]]; then
    if database_auth_probe; then
      db_auth_state="READY"
    else
      db_auth_state="$DB_AUTH_STATUS"
    fi
  fi

  ui_section "SYSTEM STATUS"
  ui_state_line "Bot" "$bot_state"
  ui_state_line "PostgreSQL" "$db_state"
  ui_state_line "Database volume" "$volume_state"
  ui_state_line "Database auth" "$db_auth_state"
  ui_state_line "Docker / Compose" "$docker_state"
  ui_state_line "Installation" "$install_state"

  ui_section "SOURCE"
  ui_kv "Project version" "${version:-unknown}"
  ui_kv "Git branch" "$branch"
  ui_kv "Git commit" "$sha"

  if env_file_valid_shape; then
    safe_config_summary
  fi
}

view_logs() {
  check_compose_prereqs || return 1
  if ! bot_running; then
    warn "Bot is not currently running; showing the latest stored logs."
    compose logs --no-color --tail 200 bot
    return 0
  fi
  say "Following bot logs. Press Ctrl+C to return."
  compose logs --no-color --tail 200 -f bot
}

rollback_source_before_migration() {
  local old_sha="$1" was_running="$2"
  warn "Rolling source back because the update failed before database migration."
  git -C "$ROOT" reset --hard "$old_sha" >/dev/null || {
    fail "Automatic source rollback failed. Bot remains stopped."
    return 1
  }
  if docker_ready && env_file_valid_shape; then
    compose build bot >/dev/null 2>&1 || true
    if [[ "$was_running" == "1" ]]; then
      compose up -d --wait postgres >/dev/null 2>&1 || true
      compose up -d --no-deps bot >/dev/null 2>&1 || true
    fi
  fi
  ok "Source returned to $old_sha."
}

update_bot() {
  local old_sha new_sha branch was_running=0

  require_command git || return 1
  repo_is_git_checkout || { fail "Update requires an official Git checkout."; return 1; }
  official_remote_ok || { fail "Origin is not the official NASERI CODER repository."; return 1; }
  branch="$(git_branch)"
  [[ "$branch" == "main" ]] || {
    fail "Safe update is allowed only from the main branch; current branch: $branch"
    return 1
  }
  [[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ]] || {
    fail "Working tree is not clean. Commit/remove local changes before update."
    return 1
  }

  ui_step 1 7 "Checking official origin/main"
  git -C "$ROOT" fetch --prune origin main || return 1
  ui_step_done "Official origin/main fetched"
  old_sha="$(git -C "$ROOT" rev-parse HEAD)"
  new_sha="$(git -C "$ROOT" rev-parse origin/main)"

  if [[ "$old_sha" == "$new_sha" ]]; then
    ok "Already up to date."
    return 0
  fi
  git -C "$ROOT" merge-base --is-ancestor "$old_sha" "$new_sha" || {
    fail "Remote history is not a fast-forward of this installation. Automatic update refused."
    return 1
  }

  ui_section "UPDATE PLAN"
  ui_kv "Current commit" "${old_sha:0:12}"
  ui_kv "Target commit" "${new_sha:0:12}"
  ui_kv "Source strategy" "FAST-FORWARD ONLY"
  ui_kv "Database backup" "MANDATORY WHEN INSTALLED"
  ui_kv "Runtime state" "RESTORED AFTER VALIDATION"
  confirm_phrase "Update will create a backup, stop the bot if running, fast-forward source, rebuild, migrate, verify, and restore the previous running state." "UPDATE" || return 1

  if env_file_valid_shape && docker_ready && volume_exists; then
    bot_running && was_running=1
    ui_step 2 7 "Creating mandatory pre-update backup"
    create_backup "pre-update" "full" || {
      fail "Pre-update backup failed. Update refused."
      return 1
    }
    ui_step_done "Pre-update backup created"
    compose stop bot >/dev/null 2>&1 || true
  else
    ui_step 2 7 "Checking backup requirement"
    ui_step_done "No installed database backup was required"
  fi

  ui_step 3 7 "Fast-forwarding source"
  if ! git -C "$ROOT" merge --ff-only "$new_sha"; then
    fail "Git fast-forward failed."
    return 1
  fi

  ui_step_done "Source fast-forward completed"
  ui_step 4 7 "Verifying updated source"
  if ! bash "$ROOT/scripts/verify.sh"; then
    rollback_source_before_migration "$old_sha" "$was_running"
    return 1
  fi

  ui_step_done "Updated source verification passed"
  if ! env_file_valid_shape; then
    ok "Source updated. No installed .env was present, so runtime changes were not attempted."
    return 0
  fi

  check_compose_prereqs || {
    rollback_source_before_migration "$old_sha" "$was_running"
    return 1
  }

  ui_step 5 7 "Building updated bot image"
  if ! compose build bot; then
    rollback_source_before_migration "$old_sha" "$was_running"
    return 1
  fi

  ui_step_done "Updated bot image built"
  if ! validate_current_config; then
    rollback_source_before_migration "$old_sha" "$was_running"
    return 1
  fi

  ui_step 6 7 "Starting PostgreSQL and applying Alembic migrations"
  compose up -d --wait postgres || {
    rollback_source_before_migration "$old_sha" "$was_running"
    return 1
  }

  # From this point onward the database may have changed. Do not perform an
  # automatic source-only rollback that could make code/schema incompatible.
  if ! compose run --rm --no-deps bot python -m alembic -c alembic.ini upgrade head; then
    fail "Migration failed. Bot remains stopped. The pre-update backup is preserved for recovery."
    return 1
  fi
  ui_step_done "Database migration reached current Alembic head"
  ui_step 7 7 "Running final application checks"
  if ! compose run --rm --no-deps bot python -m app --check-config; then
    fail "Updated configuration check failed after migration. Bot remains stopped."
    return 1
  fi
  if ! require_database_auth || ! run_app_database_check; then
    fail "Updated database check failed after migration. Bot remains stopped."
    return 1
  fi

  if [[ "$was_running" == "1" ]]; then
    compose up -d --no-deps bot || return 1
    ui_step_done "Application checks passed and previous RUNNING state restored"
    ok "Update completed and the bot was restarted."
  else
    ui_step_done "Application checks passed; previous STOPPED state preserved"
    ok "Update completed. Bot was previously stopped and remains stopped."
  fi
}

validate_configuration_action() {
  validate_current_config || return 1
  ok "Configuration validation passed."
}

configuration_menu() {
  local choice editor
  while true; do
    banner
    ui_section "CONFIGURATION"
    cat <<'MENU'
[1] Show safe configuration summary
[2] Validate configuration
[3] Edit .env with local editor
[4] Create .env on a fresh configuration
[0] Back
MENU
    ui_rule
    ui_prompt
    printf 'Select an option: '
    read -r choice
    case "$choice" in
      1) menu_action safe_config_summary ;;
      2) menu_action validate_configuration_action ;;
      3)
        env_file_valid_shape || { warn "No .env file exists."; pause_screen; continue; }
        editor="${EDITOR:-vi}"
        [[ "$editor" != *" "* ]] || { fail "EDITOR containing arguments is refused; use a simple executable name."; pause_screen; continue; }
        command_exists "$editor" || { fail "Editor not found: $editor"; pause_screen; continue; }
        warn "The editor will display local secrets. Do not copy or commit .env."
        if confirm_phrase "Open the private .env file?" "EDIT-CONFIG"; then
          if ! "$editor" "$ROOT/.env"; then
            warn "Editor exited with an error; configuration was not validated."
          fi
          chmod 600 "$ROOT/.env"
        fi
        pause_screen
        ;;
      4)
        if [[ -e "$ROOT/.env" ]]; then
          warn ".env already exists; refusing to overwrite it."
        else
          python3 "$ROOT/scripts/bootstrap_env.py" "$ROOT/.env" "$ROOT/.env.example"
        fi
        pause_screen
        ;;
      0) return 0 ;;
      *) warn "Invalid selection."; pause_screen ;;
    esac
  done
}

doctor_check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    ok "$label"
    return 0
  fi
  fail "$label"
  return 1
}

doctor() {
  local failures=0 available_kb
  banner
  ui_section "DOCTOR / DIAGNOSE"

  doctor_check "Bash available" command_exists bash || ((failures+=1))
  doctor_check "Python 3 available" command_exists python3 || ((failures+=1))
  doctor_check "sha256sum available" command_exists sha256sum || ((failures+=1))
  doctor_check "Git available" command_exists git || ((failures+=1))
  doctor_check "Repository static verification" bash "$ROOT/scripts/verify.sh" || ((failures+=1))

  if env_file_valid_shape; then
    ok "Private .env exists and is not a symlink"
    local mode_bits
    mode_bits="$(stat -c '%a' "$ROOT/.env" 2>/dev/null || true)"
    if [[ "$mode_bits" == "600" ]]; then
      ok ".env permissions are 600"
    else
      fail ".env permissions must be 600 (found: ${mode_bits:-unknown})"
      ((failures+=1))
    fi
  else
    warn ".env is not present yet"
  fi

  if docker_ready; then
    ok "Docker Engine and Compose v2 are reachable"
    if env_file_valid_shape; then
      if compose config --quiet >/dev/null 2>&1; then
        ok "Compose configuration is valid"
      else
        fail "Compose configuration is invalid"
        ((failures+=1))
      fi
      volume_exists && ok "Database volume exists" || warn "Database volume does not exist yet"
      if postgres_running; then
        ok "PostgreSQL is running"
        if database_auth_probe; then
          ok "Database credentials match the existing PostgreSQL volume"
        else
          report_database_auth_failure
          ((failures+=1))
        fi
      else
        warn "PostgreSQL is not running"
      fi
      bot_running && ok "Bot is running" || warn "Bot is not running"
    fi
  else
    warn "Docker is unavailable; runtime checks skipped"
  fi

  available_kb="$(df -Pk "$ROOT" 2>/dev/null | awk 'NR==2 {print $4}')"
  if [[ "$available_kb" =~ ^[0-9]+$ && "$available_kb" -ge 2097152 ]]; then
    ok "At least 2 GiB disk space is available"
  else
    warn "Less than 2 GiB free disk space or disk size could not be read"
  fi

  if [[ "$failures" -eq 0 ]]; then
    ok "Doctor completed without hard failures."
  else
    fail "Doctor found $failures hard failure(s)."
    return 1
  fi
}

verify_installation() {
  bash "$ROOT/scripts/verify.sh" || return 1
  ok "Repository verification passed."

  if ! env_file_valid_shape; then
    warn "No installation configuration exists yet; runtime verification skipped."
    return 0
  fi
  check_compose_prereqs || return 1
  validate_current_config || return 1

  if ! volume_exists; then
    warn "No database volume exists yet; installation is not complete."
    return 0
  fi

  compose up -d --wait postgres >/dev/null || return 1
  compose run --rm --no-deps bot python -m alembic -c alembic.ini current || return 1
  compose run --rm --no-deps bot python -m alembic -c alembic.ini heads || return 1
  compose run --rm --no-deps bot python -m app --check-config || return 1
  require_database_auth || return 1
  run_app_database_check || return 1
  ok "Installation verification passed."
}

system_information() {
  banner
  ui_section "SYSTEM INFORMATION"
  printf '  OS...................... %s\n' "$(uname -srm 2>/dev/null || printf unknown)"
  printf '  Architecture............ %s\n' "$(uname -m 2>/dev/null || printf unknown)"
  if command_exists nproc; then
    printf '  CPU threads.............. %s\n' "$(nproc)"
  fi
  if [[ -r /proc/meminfo ]]; then
    printf '  Memory................... %s kB total\n' "$(awk '/MemTotal:/ {print $2; exit}' /proc/meminfo)"
  fi
  printf '  Disk free................ %s kB\n' "$(df -Pk "$ROOT" 2>/dev/null | awk 'NR==2 {print $4}')"
  printf '  Docker................... %s\n' "$(docker --version 2>/dev/null || printf unavailable)"
  printf '  Compose.................. %s\n' "$(docker compose version --short 2>/dev/null || printf unavailable)"
  printf '  Project version.......... %s\n' "$(project_version)"
  printf '  Installation state....... %s\n' "$(installation_state)"
}

uninstall_bot() {
  local choice
  check_compose_prereqs || return 1
  banner
  ui_section_danger "UNINSTALL / REMOVE RUNTIME"
  cat <<'MENU'
[1] Remove bot container only
    Keep PostgreSQL, database volume, .env, backups and source.

[2] Remove project containers/network
    Keep database volume, .env, backups and source.

[3] FULL RUNTIME REMOVE
    Remove project containers, network and database volume.
    Keep source and backups. Remove .env only after a second confirmation.

[0] Cancel
MENU
  ui_rule
  ui_prompt
  printf 'Select an option: '
  read -r choice
  case "$choice" in
    1)
      confirm_phrase "Remove only the bot container?" "REMOVE-BOT" || return 1
      compose rm -sf bot
      ok "Bot container removed; persistent database retained."
      ;;
    2)
      confirm_phrase "Remove project containers/network while retaining persistent data?" "REMOVE-CONTAINERS" || return 1
      compose down --remove-orphans
      ok "Containers/network removed; database volume and configuration retained."
      ;;
    3)
      confirm_phrase "This permanently removes the project database volume." "DELETE-RUNTIME-DATA" || return 1
      compose down --volumes --remove-orphans
      ok "Runtime containers/network/database volume removed."
      if confirm_phrase "Optionally remove the private .env file too. Backups and source will remain." "DELETE-CONFIG"; then
        rm -f -- "$ROOT/.env"
        ok "Private .env removed."
      else
        warn ".env retained."
      fi
      ;;
    0) warn "Cancelled." ;;
    *) fail "Invalid selection."; return 1 ;;
  esac
}


environment_check() {
  local failures=0 mode_bits
  banner
  ui_section "ENVIRONMENT CHECK"

  for cmd in bash python3 sha256sum git; do
    if command_exists "$cmd"; then
      ok "$cmd is available"
    else
      fail "$cmd is missing"
      ((failures+=1))
    fi
  done

  if docker_ready; then
    ok "Docker Engine and Compose v2 are reachable"
  else
    warn "Docker Engine/Compose is unavailable or daemon access is missing"
  fi

  if env_file_valid_shape; then
    ok ".env exists and is not a symlink"
    mode_bits="$(stat -c '%a' "$ROOT/.env" 2>/dev/null || true)"
    if [[ "$mode_bits" == "600" ]]; then
      ok ".env permissions are 600"
    else
      fail ".env permissions must be 600 (found: ${mode_bits:-unknown})"
      ((failures+=1))
    fi
    if validate_current_config >/dev/null 2>&1; then
      ok "Configuration contract is valid"
    else
      fail "Configuration contract validation failed"
      ((failures+=1))
    fi
  else
    warn ".env has not been created yet"
  fi

  if [[ "$failures" -eq 0 ]]; then
    ok "Environment check completed without hard failures."
  else
    fail "Environment check found $failures hard failure(s)."
    return 1
  fi
}

database_status() {
  check_compose_prereqs || return 1
  if volume_exists; then
    ok "Database volume exists."
  else
    warn "Database volume does not exist yet."
    return 0
  fi
  postgres_running && ok "PostgreSQL is running." || warn "PostgreSQL is stopped."
}

database_migrations() {
  check_compose_prereqs || return 1
  volume_exists || { warn "Database volume does not exist yet."; return 0; }

  info "Repository migration head:"
  compose run --rm --no-deps bot python -m alembic -c alembic.ini heads || return 1

  if postgres_running; then
    info "Current database revision:"
    compose run --rm --no-deps bot python -m alembic -c alembic.ini current
  else
    warn "PostgreSQL is stopped; current database revision was not queried."
  fi
}

database_upgrade_head() {
  local was_bot_running=0
  check_compose_prereqs || return 1
  volume_exists || { fail "Database volume does not exist."; return 1; }
  bot_running && was_bot_running=1

  confirm_phrase \
    "This creates a mandatory backup, stops the bot, rebuilds verified source, upgrades Alembic to head, verifies the DB, then restores the prior running state." \
    "UPGRADE-DATABASE" || return 1

  create_backup "pre-db-upgrade" "full" || {
    fail "Mandatory backup failed; database upgrade refused."
    return 1
  }

  compose stop bot >/dev/null 2>&1 || true
  bash "$ROOT/scripts/verify.sh" || {
    fail "Source verification failed; database upgrade refused."
    restore_previous_bot_container "$was_bot_running"
    return 1
  }
  compose build bot || {
    fail "Bot image build failed; database upgrade refused."
    restore_previous_bot_container "$was_bot_running"
    return 1
  }
  validate_current_config || {
    fail "Current configuration is invalid for the rebuilt image; database upgrade refused."
    restore_previous_bot_container "$was_bot_running"
    return 1
  }
  compose up -d --wait postgres >/dev/null || {
    restore_previous_bot_container "$was_bot_running"
    return 1
  }

  if ! compose run --rm --no-deps bot python -m alembic -c alembic.ini upgrade head; then
    fail "Database migration failed. Bot remains stopped and the backup is preserved."
    return 1
  fi
  if ! require_database_auth || ! run_app_database_check; then
    fail "Database verification failed. Bot remains stopped and the backup is preserved."
    return 1
  fi

  if [[ "$was_bot_running" == "1" ]]; then
    compose up -d --no-deps bot || return 1
    ok "Database upgraded and bot restarted."
  else
    ok "Database upgraded. Bot was previously stopped and remains stopped."
  fi
}

database_menu() {
  local choice dir
  while true; do
    banner
    ui_section "DATABASE MANAGEMENT"
    cat <<'MENU'
[1] Database status
[2] Show current migration / head
[3] Upgrade database to Alembic head
[4] Create database backup
[5] Restore database backup
[0] Back
MENU
    ui_rule
    ui_prompt
    printf 'Select an option: '
    read -r choice
    case "$choice" in
      1) menu_action database_status ;;
      2) menu_action database_migrations ;;
      3) menu_locked_action database_upgrade_head ;;
      4) menu_locked_action create_backup "manual-db" "database" ;;
      5)
        if select_backup_dir; then
          menu_locked_action restore_database_from_dir "$SELECTED_BACKUP_DIR"
        else
          menu_action false
        fi
        ;;
      0) return 0 ;;
      *) warn "Invalid selection."; pause_screen ;;
    esac
  done
}

repair_env_permissions() {
  env_file_valid_shape || { fail ".env missing or unsafe; nothing to repair."; return 1; }
  chmod 600 "$ROOT/.env"
  ok ".env permissions set to 600."
}

repair_rebuild_bot() {
  local was_running=0
  check_compose_prereqs || return 1
  bot_running && was_running=1
  confirm_phrase \
    "Rebuild the bot image from the current verified source and run configuration/database checks?" \
    "REBUILD-BOT" || return 1

  compose stop bot >/dev/null 2>&1 || true
  bash "$ROOT/scripts/verify.sh" || {
    fail "Source verification failed; rebuild refused."
    restore_previous_bot_container "$was_running"
    return 1
  }
  compose build bot || {
    restore_previous_bot_container "$was_running"
    return 1
  }
  validate_current_config || {
    fail "Rebuilt image rejected the current configuration."
    restore_previous_bot_container "$was_running"
    return 1
  }

  if volume_exists; then
    compose up -d --wait postgres >/dev/null || {
      restore_previous_bot_container "$was_running"
      return 1
    }
    compose run --rm --no-deps bot python -m app --check-config || {
      restore_previous_bot_container "$was_running"
      return 1
    }
    require_database_auth || {
      restore_previous_bot_container "$was_running"
      return 1
    }
    run_app_database_check || {
      restore_previous_bot_container "$was_running"
      return 1
    }
  fi

  if [[ "$was_running" == "1" ]]; then
    compose up -d --no-deps bot || return 1
    ok "Bot image rebuilt, verified and restarted."
  else
    ok "Bot image rebuilt and verified. Bot remains stopped."
  fi
}

repair_database_credentials() {
  local was_running=0

  check_compose_prereqs || return 1
  volume_exists || { fail "Database volume does not exist."; return 1; }
  validate_current_config || return 1

  compose up -d --wait postgres >/dev/null || return 1

  if database_auth_probe; then
    ok "Database credentials already match the existing PostgreSQL volume. No repair is needed."
    return 0
  fi

  if [[ "$DB_AUTH_STATUS" != "PASSWORD_MISMATCH" ]]; then
    report_database_auth_failure
    fail "Automatic credential repair is allowed only for a confirmed password mismatch."
    return 1
  fi

  bot_running && was_running=1

  ui_section "DATABASE CREDENTIAL RECOVERY"
  ui_kv "Detected issue" "PASSWORD_MISMATCH"
  ui_kv "Database volume" "PRESERVED"
  ui_kv "Database contents" "NOT DELETED"
  ui_kv "Safety backup" "MANDATORY"

  confirm_phrase \
    "This will back up the current database and change only the existing PostgreSQL role password to match the private .env configuration." \
    "REPAIR-DATABASE-CREDENTIALS" || return 1

  create_backup "pre-db-credential-repair" "full" || {
    fail "Safety backup failed. Database credential repair was refused."
    return 1
  }

  compose stop bot >/dev/null 2>&1 || true

  info "Synchronizing the existing PostgreSQL role password with the private configuration..."
  if ! compose exec -T postgres sh -c \
    'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
\getenv nc_role POSTGRES_USER
\getenv nc_password POSTGRES_PASSWORD
SELECT format('ALTER ROLE %I WITH PASSWORD %L', :'nc_role', :'nc_password') \gexec
SQL
  then
    fail "PostgreSQL rejected credential repair. Database contents were not deleted."
    restore_previous_bot_container "$was_running"
    return 1
  fi

  if ! database_auth_probe; then
    report_database_auth_failure
    fail "Credential repair did not produce a valid authenticated connection."
    return 1
  fi

  if ! run_app_database_check; then
    fail "Credential repair succeeded at PostgreSQL but the application database check still failed."
    return 1
  fi

  if [[ "$was_running" == "1" ]]; then
    compose start bot >/dev/null || return 1
    ok "Database credentials repaired and previous RUNNING state restored."
  else
    ok "Database credentials repaired. Bot remains stopped; use Start Bot when ready."
  fi
}

repair_menu() {
  local choice
  while true; do
    banner
    ui_section "REPAIR / DIAGNOSE"
    cat <<'MENU'
[1] Run Doctor
[2] Repair .env permissions
[3] Rebuild and verify bot image
[4] Restart bot safely
[5] Repair database credentials
[0] Back
MENU
    ui_rule
    ui_prompt
    printf 'Select an option: '
    read -r choice
    case "$choice" in
      1) menu_action doctor ;;
      2) menu_locked_action repair_env_permissions ;;
      3) menu_locked_action repair_rebuild_bot ;;
      4) menu_locked_action restart_bot ;;
      5) menu_locked_action repair_database_credentials ;;
      0) return 0 ;;
      *) warn "Invalid selection."; pause_screen ;;
    esac
  done
}

maintenance_menu() {
  local choice
  while true; do
    banner
    ui_section "MAINTENANCE"
    cat <<'MENU'
[1] Doctor / Diagnose
[2] Verify installation
[3] Show system information
[4] Validate configuration
[5] Show status
[0] Back
MENU
    ui_rule
    ui_prompt
    printf 'Select an option: '
    read -r choice
    case "$choice" in
      1) menu_action doctor ;;
      2) menu_action verify_installation ;;
      3) menu_action system_information ;;
      4) menu_action validate_configuration_action ;;
      5) menu_action show_status ;;
      0) return 0 ;;
      *) warn "Invalid selection."; pause_screen ;;
    esac
  done
}
