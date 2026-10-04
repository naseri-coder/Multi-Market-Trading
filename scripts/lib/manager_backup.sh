#!/usr/bin/env bash

# Backup and restore helpers for NASERI CODER Bot Manager.
# shellcheck shell=bash

timestamp_utc() {
  date -u '+%Y%m%dT%H%M%SZ'
}

new_backup_dir() {
  local label="${1:-manual}" stamp base dir suffix=0
  stamp="$(timestamp_utc)"
  mkdir -p "$BACKUP_ROOT"
  chmod 700 "$BACKUP_ROOT"
  base="$BACKUP_ROOT/${stamp}-${label}"
  dir="$base"
  while ! mkdir -m 700 "$dir" 2>/dev/null; do
    ((suffix+=1))
    (( suffix <= 100 )) || { fail "Could not allocate a unique backup directory."; return 1; }
    dir="${base}-${suffix}"
  done
  printf '%s' "$dir"
}

write_backup_metadata() {
  local dir="$1" kind="$2"
  {
    printf 'created_utc=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf 'kind=%s\n' "$kind"
    printf 'project=%s\n' "$PROJECT_NAME"
    printf 'version=%s\n' "$(project_version)"
    printf 'git_branch=%s\n' "$(git_branch)"
    printf 'git_commit=%s\n' "$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || printf unknown)"
  } > "$dir/metadata.txt"
  chmod 600 "$dir/metadata.txt"
}

backup_config_to_dir() {
  local dir="$1"
  if env_file_valid_shape; then
    cp -- "$ROOT/.env" "$dir/env.backup"
    chmod 600 "$dir/env.backup"
    ok "Configuration backup created (contents not displayed)."
  else
    warn "No safe .env file found; configuration backup skipped."
  fi
}

backup_database_to_dir() {
  local dir="$1" was_running=0
  check_compose_prereqs || return 1
  volume_exists || { warn "Database volume does not exist; database backup skipped."; return 0; }
  postgres_running && was_running=1

  if ! postgres_running; then
    info "Starting PostgreSQL temporarily for backup..."
    compose up -d --wait postgres >/dev/null || return 1
  fi

  info "Creating PostgreSQL custom-format dump..."
  if ! compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$dir/database.dump"; then
    rm -f -- "$dir/database.dump"
    [[ "$was_running" == 1 ]] || compose stop postgres >/dev/null 2>&1 || true
    fail "Database backup failed."
    return 1
  fi
  chmod 600 "$dir/database.dump"
  [[ -s "$dir/database.dump" ]] || { fail "Database dump is empty."; return 1; }

  if [[ "$was_running" == 0 ]]; then
    compose stop postgres >/dev/null || true
  fi
  ok "Database backup created."
}

create_backup() {
  local label="${1:-manual}" kind="${2:-full}" dir
  dir="$(new_backup_dir "$label")"
  write_backup_metadata "$dir" "$kind"

  case "$kind" in
    full)
      backup_config_to_dir "$dir"
      if docker_ready && volume_exists; then
        backup_database_to_dir "$dir" || { fail "Backup incomplete: $dir"; return 1; }
      else
        warn "No Docker database volume detected; database dump skipped."
      fi
      ;;
    config)
      backup_config_to_dir "$dir"
      ;;
    database)
      backup_database_to_dir "$dir" || { fail "Backup incomplete: $dir"; return 1; }
      ;;
    *)
      fail "Unknown backup kind: $kind"
      return 1
      ;;
  esac

  ok "Backup stored at: $dir"
  printf '%s\n' "$dir"
}

list_backups() {
  mkdir -p "$BACKUP_ROOT"
  chmod 700 "$BACKUP_ROOT"
  local found=0 path
  ui_section "AVAILABLE BACKUPS"
  while IFS= read -r -d '' path; do
    found=1
    printf '  %s\n' "$(basename "$path")"
  done < <(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z -r)
  [[ "$found" == 1 ]] || say "  (none)"
}

SELECTED_BACKUP_DIR=""

select_backup_dir() {
  local -a dirs=()
  local path choice i=1
  SELECTED_BACKUP_DIR=""
  while IFS= read -r -d '' path; do
    dirs+=("$path")
  done < <(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null | sort -z -r)

  (("${#dirs[@]}" > 0)) || { warn "No backups are available."; return 1; }
  is_tty || { fail "Interactive backup selection required."; return 1; }

  ui_section "SELECT BACKUP"
  for path in "${dirs[@]}"; do
    printf '  [%d] %s\n' "$i" "$(basename "$path")"
    ((i+=1))
  done
  read -r -p "Backup number: " choice
  [[ "$choice" =~ ^[0-9]+$ ]] || return 1
  (( choice >= 1 && choice <= ${#dirs[@]} )) || return 1
  SELECTED_BACKUP_DIR="${dirs[choice-1]}"
  return 0
}

restore_database_from_dir() {
  local dir="$1" was_bot_running=0
  [[ -f "$dir/database.dump" && ! -L "$dir/database.dump" ]] || {
    fail "Selected backup has no valid database.dump."
    return 1
  }
  check_compose_prereqs || return 1
  volume_exists || { fail "Database volume does not exist."; return 1; }
  bot_running && was_bot_running=1

  confirm_phrase     "Database restore will replace database objects from the selected dump. A safety backup is created first."     "RESTORE-DATABASE" || return 1

  create_backup "pre-restore" "full" >/dev/null || {
    fail "Safety backup failed; restore refused."
    return 1
  }

  compose stop bot >/dev/null 2>&1 || true
  compose up -d --wait postgres >/dev/null || return 1

  info "Restoring database. Existing objects may be replaced..."
  if ! compose exec -T postgres sh -c \
    'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges' \
    < "$dir/database.dump"; then
    fail "Database restore failed. Bot remains stopped; use the pre-restore backup to recover."
    return 1
  fi

  compose run --rm --no-deps bot python -m alembic -c alembic.ini upgrade head || {
    fail "Post-restore migration failed. Bot remains stopped."
    return 1
  }
  compose run --rm --no-deps bot python -m app --check-db || {
    fail "Post-restore database check failed. Bot remains stopped."
    return 1
  }

  if [[ "$was_bot_running" == 1 ]]; then
    compose up -d --no-deps bot
    ok "Database restored and bot restarted."
  else
    ok "Database restored. Bot was previously stopped and remains stopped."
  fi
}

restore_config_from_dir() {
  local dir="$1" tmp current_backup=""
  [[ -f "$dir/env.backup" && ! -L "$dir/env.backup" ]] || {
    fail "Selected backup has no valid env.backup."
    return 1
  }
  confirm_phrase     "Configuration restore replaces .env. Database credentials must still match the existing database volume."     "RESTORE-CONFIG" || return 1

  tmp="$ROOT/.env.restore.$$"
  if env_file_valid_shape; then
    current_backup="$ROOT/.env.before-restore.$$"
    cp -- "$ROOT/.env" "$current_backup"
    chmod 600 "$current_backup"
  fi

  cp -- "$dir/env.backup" "$tmp"
  chmod 600 "$tmp"
  mv -- "$tmp" "$ROOT/.env"
  chmod 600 "$ROOT/.env"

  if ! validate_current_config; then
    if [[ -n "$current_backup" && -f "$current_backup" ]]; then
      mv -- "$current_backup" "$ROOT/.env"
      chmod 600 "$ROOT/.env"
    else
      rm -f -- "$ROOT/.env"
    fi
    fail "Restored configuration failed validation; previous configuration was reinstated."
    return 1
  fi

  if docker_ready && volume_exists && postgres_running; then
    if ! compose run --rm --no-deps bot python -m app --check-db >/dev/null; then
      if [[ -n "$current_backup" && -f "$current_backup" ]]; then
        mv -- "$current_backup" "$ROOT/.env"
        chmod 600 "$ROOT/.env"
      fi
      fail "Restored configuration cannot connect to the current database; previous configuration was reinstated."
      return 1
    fi
  fi

  [[ -n "$current_backup" ]] && rm -f -- "$current_backup"
  ok "Configuration restored and validated. Restart the bot to apply it."
}


backup_create_menu() {
  local choice
  while true; do
    banner
    ui_section "BACKUP"
    cat <<'MENU'
[1] Create full backup
[2] Create database backup
[3] Create configuration backup
[4] List backups
[0] Back
MENU
    ui_rule
    ui_prompt
    printf 'Select an option: '
    read -r choice
    case "$choice" in
      1) menu_locked_action create_backup "manual" "full" ;;
      2) menu_locked_action create_backup "manual-db" "database" ;;
      3) menu_locked_action create_backup "manual-config" "config" ;;
      4) menu_action list_backups ;;
      0) return 0 ;;
      *) warn "Invalid selection."; pause_screen ;;
    esac
  done
}

restore_menu() {
  local choice dir
  while true; do
    banner
    ui_section "RESTORE"
    cat <<'MENU'
[1] Restore database
[2] Restore configuration
[3] List backups
[0] Back
MENU
    ui_rule
    ui_prompt
    printf 'Select an option: '
    read -r choice
    case "$choice" in
      1)
        if select_backup_dir; then
          menu_locked_action restore_database_from_dir "$SELECTED_BACKUP_DIR"
        else
          menu_action false
        fi
        ;;
      2)
        if select_backup_dir; then
          menu_locked_action restore_config_from_dir "$SELECTED_BACKUP_DIR"
        else
          menu_action false
        fi
        ;;
      3) menu_action list_backups ;;
      0) return 0 ;;
      *) warn "Invalid selection."; pause_screen ;;
    esac
  done
}

backup_menu() {
  local choice dir
  while true; do
    banner
    ui_section "BACKUP & RESTORE"
    cat <<'MENU'
[1] Create full backup
[2] Create database backup
[3] Create configuration backup
[4] List backups
[5] Restore database
[6] Restore configuration
[0] Back
MENU
    ui_rule
    ui_prompt
    printf 'Select an option: '
    read -r choice
    case "$choice" in
      1) menu_locked_action create_backup "manual" "full" ;;
      2) menu_locked_action create_backup "manual-db" "database" ;;
      3) menu_locked_action create_backup "manual-config" "config" ;;
      4) menu_action list_backups ;;
      5)
        if select_backup_dir; then
          menu_locked_action restore_database_from_dir "$SELECTED_BACKUP_DIR"
        else
          menu_action false
        fi
        ;;
      6)
        if select_backup_dir; then
          menu_locked_action restore_config_from_dir "$SELECTED_BACKUP_DIR"
        else
          menu_action false
        fi
        ;;
      0) return 0 ;;
      *) warn "Invalid selection."; pause_screen ;;
    esac
  done
}
