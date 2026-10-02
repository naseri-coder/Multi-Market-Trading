# Phase 16 — Notification Settings

## Scope

Phase 16 adds persistent, per-user controls for six notification categories:

- `NEW_SIGNAL`
- `TARGET_HIT`
- `STOP_HIT`
- `SIGNAL_UPDATED`
- `SIGNAL_CLOSED`
- `SYSTEM_NOTIFICATION`

This phase stores and presents user preferences only. Actual event delivery,
fan-out, retry behavior, and Telegram notifications remain owned by Phase 21.

## Default and Mutation Semantics

All six categories are enabled by default. Opening the settings interface
atomically inserts only missing rows, so an older user automatically receives
defaults for newly introduced supported categories without overwriting any
existing choice.

Callbacks express the intended final state (`enable` or `disable`) instead of
performing a blind toggle. Replaying the same callback is therefore idempotent
and cannot accidentally reverse a user's choice.

## Database

`user_notification_settings` contains:

- bigint identity `id`;
- `user_id`, referencing `users.id` with `ON DELETE CASCADE`;
- allow-listed `notification_type`;
- non-null `is_enabled`, defaulting to true;
- aware `created_at` and `updated_at` timestamps;
- a unique pair `(user_id, notification_type)`.

The `(notification_type, is_enabled, user_id)` index is reserved for efficient
recipient selection by the Phase 21 delivery service. The unique pair also
supports direct lookup of one user's complete settings.

## Layers

- `app/modules/notifications/models.py`: enum and persistent model.
- `app/modules/notifications/repository.py`: PostgreSQL upsert and reads.
- `app/modules/notifications/service.py`: defaults, validation, and idempotency.
- `app/bot/handlers/notification_settings_user.py`: Telegram access adapter.
- `app/bot/keyboards/notifications.py`: exact callbacks and Persian controls.
- `migrations/versions/20260902_0008_create_user_notification_settings.py`:
  schema migration.

## Security and Reliability

- The channel-membership gate and user activity sync run before every action.
- Callback payloads are anchored, versioned, under Telegram's byte limit, and
  allow only the six supported categories and two explicit states.
- Database uniqueness prevents duplicate preferences.
- The notification-type check constraint rejects unsupported persisted values.
- Repository exceptions are mapped without exposing database error details.
- User deletion cascades to all owned preferences.

## Verification

Unit coverage includes default creation, preservation of disabled values,
idempotent writes, user isolation, malformed input, aware clocks, repository
error mapping, exact callbacks, access gates, rendering, menus, ORM metadata,
Migration chain, and application handler order. A real PostgreSQL integration
test verifies self-healing defaults, constraints, uniqueness, user isolation,
Cascade deletion, and transaction rollback.
