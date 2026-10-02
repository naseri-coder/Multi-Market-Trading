# Phase 15 — Favorites

## Scope

Phase 15 adds per-user Signal bookmarks. Users can add or remove a public
Signal from its detail page and browse their saved Signals through the
`⭐ علاقه‌مندی‌ها` menu entry. This phase does not add notification settings or
notification delivery behavior.

## Database

The `user_favorites` association table contains:

- a bigint identity primary key;
- `user_id`, referencing `users.id` with `ON DELETE CASCADE`;
- `signal_id`, referencing `signals.id` with `ON DELETE CASCADE`;
- an aware `created_at` timestamp;
- a database-enforced unique pair `(user_id, signal_id)`.

The `(user_id, created_at, id)` index supports stable newest-first pagination.
The `signal_id` index supports reverse lookup and cascade maintenance.

## Business Rules

- A user can favorite only an existing non-Draft Signal.
- Adding the same Signal repeatedly is idempotent and creates one row.
- Removing an absent favorite is harmless.
- Favorites are isolated by the internal user ID.
- Draft Signals are excluded from both add validation and list queries.
- Deleting a user or Signal removes its favorite associations in PostgreSQL.
- The list is fetched from PostgreSQL in pages of exactly 10 items.
- A page beyond the last page is clamped to the current last page.

## Telegram Interface

- The user menu exposes `⭐ علاقه‌مندی‌ها`.
- Public Signal detail pages expose one star action whose state is loaded for
  the current user.
- Favorite details retain target pagination and a stable return to the
  originating favorite page.
- Callback payloads use an anchored, versioned allowlist separate from Signal
  list callbacks.
- The existing multi-channel membership gate and user activity refresh are
  applied before every favorite operation.

## Layers

- `app/modules/favorites/models.py`: persistent association.
- `app/modules/favorites/repository.py`: parameterized PostgreSQL queries.
- `app/modules/favorites/service.py`: validation, idempotency, and pagination.
- `app/bot/handlers/favorites_user.py`: public Telegram adapter.
- `app/bot/keyboards/favorites.py`: exact callback and keyboard builders.
- `migrations/versions/20260901_0007_create_user_favorites.py`: schema change.

## Verification

Unit tests cover idempotent mutations, invalid identifiers, Draft visibility,
user isolation, pagination, callback tamper resistance, decimal rendering,
Telegram access gates, menu integration, model metadata, and migration layout.
The PostgreSQL integration test additionally verifies the unique pair,
10-item pages, transaction rollback, user isolation, and user/Signal cascades.
