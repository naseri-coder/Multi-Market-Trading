# Brooks Books v2 — Shadow-Only Overlay

This overlay adds a new book-grounded Brooks H2/L2 continuation core without deleting or
replacing the existing Phase 7/8 engine.

Safety defaults:

- autonomous LONG/SHORT: disabled
- DB writes: none
- Telegram publishing: none
- PAPER runtime: untouched
- migration changes: none
- requirements changes: none

Files added under `app/modules/brooks_core/`:

- `books_policy.py`
- `books_entities.py`
- `context_classifier.py`
- `second_entry_v2.py`
- `books_engine.py`

The existing `fundamentals_engine.py`, `second_entry.py`, `pullback_guard.py`, runtime
wiring, DB, and Telegram handlers are not changed by the overlay.

Before production wiring, run replay/holdout validation. The engine returns NO_SIGNAL by
default even when it detects `H2_CONFIRMED` or `L2_CONFIRMED`.
