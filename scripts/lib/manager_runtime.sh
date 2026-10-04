#!/usr/bin/env bash

# Runtime, update, diagnostics and uninstall workflows.
# shellcheck shell=bash

install_bot() {
  info "Launching the existing fail-closed fresh-host installer."
  bash "$ROOT/scripts/install.sh" --install
}

start_bot() {
  check_compose_prereqs || return 1
  volume_exists || {
    fail "No project database volume exists. Use Install Bot first."
    return 1
  }
  validate_current_config || return 1

  info "Starting PostgreSQL..."
  compose up -d --wait postgres || return 1
  info "Checking application configuration and database..."
  compose run --rm --no-deps bot python -m app --check-config || return 1
  compose run --rm --no-deps bot python -m app --check-db || return 1
  compose up -d --no-deps bot
  ok "Bot started."
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
  local version branch sha bot_state db_state volume_state
  version="$(project_version)"
  branch="$(git_branch)"
  sha="$(git_short_sha)"
  bot_state="STOPPED"
  db_state="STOPPED"
  volume_state="ABSENT"
  bot_running && bot_state="RUNNING"
  postgres_running && db_state="RUNNING"
  docker_ready && volume_exists && volume_state="PRESENT"

  cat <<STATUS
Bot Status

  Project version......... ${version:-unknown}
  Git branch.............. $branch
  Git commit.............. $sha
  Bot..................... $bot_state
  PostgreSQL.............. $db_state
  Database volume......... $volume_state
  Installation state...... $(installation_state)
STATUS

  if env_file_valid_shape; then
    say
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

  info "Checking the official main branch for updates..."
  git -C "$ROOT" fetch --prune origin main || return 1
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

  say "Current : ${old_sha:0:12}"
  say "Latest  : ${new_sha:0:12}"
  confirm_phrase     "Update will create a backup, stop the bot if running, fast-forward source, rebuild, migrate, verify, and restore the previous running state."     "UPDATE" || return 1

  if env_file_valid_shape && docker_ready && volume_exists; then
    bot_running && was_running=1
    info "Creating mandatory pre-update backup..."
    create_backup "pre-update" "full" || {
      fail "Pre-update backup failed. Update refused."
      return 1
    }
    compose stop bot >/dev/null 2>&1 || true
  fi

  if ! git -C "$ROOT" merge --ff-only "$new_sha"; then
    fail "Git fast-forward failed."
    return 1
  fi

  if ! bash "$ROOT/scripts/verify.sh"; then
    rollback_source_before_migration "$old_sha" "$was_running"
    return 1
  fi

  if ! env_file_valid_shape; then
    ok "Source updated. No installed .env was present, so runtime changes were not attempted."
    return 0
  fi

  check_compose_prereqs || {
    rollback_source_before_migration "$old_sha" "$was_running"
    return 1
  }

  info "Building updated bot image..."
  if ! compose build bot; then
    rollback_source_before_migration "$old_sha" "$was_running"
    return 1
  fi

  if ! validate_current_config; then
    rollback_source_before_migration "$old_sha" "$was_running"
    return 1
  fi

  info "Starting PostgreSQL and applying Alembic migrations..."
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
  if ! compose run --rm --no-deps bot python -m app --check-config; then
    fail "Updated configuration check failed after migration. Bot remains stopped."
    return 1
  fi
  if ! compose run --rm --no-deps bot python -m app --check-db; then
    fail "Updated database check failed after migration. Bot remains stopped."
    return 1
  fi

  if [[ "$was_running" == "1" ]]; then
    compose up -d --no-deps bot || return 1
    ok "Update completed and the bot was restarted."
  else
    ok "Update completed. Bot was previously stopped and remains stopped."
  fi
}

configuration_menu() {
  local choice editor
  while true; do
    banner
    cat <<'MENU'
Configuration

[1] Show safe configuration summary
[2] Validate configuration
[3] Edit .env with local editor
[4] Create .env on a fresh configuration
[0] Back
MENU
    read -r -p "Select an option: " choice
    case "$choice" in
      1) safe_config_summary; pause_screen ;;
      2) validate_current_config && ok "Configuration validation passed."; pause_screen ;;
      3)
        env_file_valid_shape || { warn "No .env file exists."; pause_screen; continue; }
        editor="${EDITOR:-vi}"
        [[ "$editor" != *" "* ]] || { fail "EDITOR containing arguments is refused; use a simple executable name."; pause_screen; continue; }
        command_exists "$editor" || { fail "Editor not found: $editor"; pause_screen; continue; }
        warn "The editor will display local secrets. Do not copy or commit .env."
        confirm_phrase "Open the private .env file?" "EDIT-CONFIG" && "$editor" "$ROOT/.env"
        chmod 600 "$ROOT/.env"
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
  say "Doctor / Diagnose"
  say

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
      postgres_running && ok "PostgreSQL is running" || warn "PostgreSQL is not running"
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
  compose run --rm --no-deps bot python -m app --check-db || return 1
  ok "Installation verification passed."
}

system_information() {
  banner
  say "System Information"
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
  cat <<'MENU'
Uninstall / Remove Runtime

[1] Remove bot container only
    Keep PostgreSQL, database volume, .env, backups and source.

[2] Remove project containers/network
    Keep database volume, .env, backups and source.

[3] FULL RUNTIME REMOVE
    Remove project containers, network and database volume.
    Keep source and backups. Remove .env only after a second confirmation.

[0] Cancel
MENU
  read -r -p "Select an option: " choice
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

maintenance_menu() {
  local choice
  while true; do
    banner
    cat <<'MENU'
Maintenance

[1] Doctor / Diagnose
[2] Verify installation
[3] Show system information
[4] Validate configuration
[5] Show status
[0] Back
MENU
    read -r -p "Select an option: " choice
    case "$choice" in
      1) doctor; pause_screen ;;
      2) verify_installation; pause_screen ;;
      3) system_information; pause_screen ;;
      4) validate_current_config && ok "Configuration validation passed."; pause_screen ;;
      5) show_status; pause_screen ;;
      0) return 0 ;;
      *) warn "Invalid selection."; pause_screen ;;
    esac
  done
}
