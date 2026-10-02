# Integration Phase 4 — PAPER Runtime Safety Wiring

## Purpose

Provide the safe persistence + delivery layer needed before a live Brooks market analyzer
is attached.

This phase adds:

- fail-closed PAPER runtime configuration
- PAPER candidate → existing BrooksSignalIntegrationService mapping
- PRIVATE_TEST-only Telegram publisher
- durable `signal_deliveries` state
- delivery duplicate guard
- fail-closed `SENDING` / `AMBIGUOUS` behavior

## Delivery semantics

External Telegram delivery cannot be globally transactional with PostgreSQL.

The runtime therefore prefers "do not automatically duplicate a possibly-sent message"
over aggressive retry:

- PENDING → SENDING → SENT
- known send failure: SENDING → FAILED (retryable)
- uncertain acknowledgement failure: SENDING → AMBIGUOUS (manual reconciliation)
- SENT is never sent again

## Safety invariants

Every PAPER signal:
- `generation_mode = PAPER`
- `publication_scope = PRIVATE_TEST`
- `counts_toward_performance = false`

No public/VIP production publication is implemented here.

## Scope boundary

This phase does not yet attach the real-time exchange adapter and full Brooks analysis
pipeline. It creates the safe runtime/publishing boundary that the analyzer will feed next.

PAPER runtime remains disabled by default.
