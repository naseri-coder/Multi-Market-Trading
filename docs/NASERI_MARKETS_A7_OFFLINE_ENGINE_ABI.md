# A7 — Offline engine ABI and replay integration

**Verdict scope:** GitHub-only software integration. No VPS, runtime installation,
live market connection, Telegram publication, broker order, real NYFR rules, or
production database migration is authorized.

## Public/private split

The public package owns the quote-quality gate, session validation,
engine registry, paper-signal validation, and durable paper journal.

`naseri_markets.external_abi` declares a strict **ABI version 1** for an
operator-injected external engine's signal envelope. It contains only engine
identity and version, instrument, time, direction, entry, stop and target(s),
all marked `paper`. It carries no source, formulas, imports, plugin URL,
execution command, subscriber token, proprietary decision traces or secret.

The public `ExternalPaperEngine` accepts an injected async
`produce(tick) -> bytes | None` provider. A **synthetic stand-in**, not
the actual NY First-Reversal strategy, supplies those bytes in CI.

A valid envelope does NOT verify that the engine was genuinely authored by
its owner, licensed, signed or isolated as a process. An injected Python
callback may perform arbitrary work; A7 is NOT a sandbox. A future stage
must independently authenticate and isolate such providers.

## Actual offline integration

`QuoteTick` with `SYNTHETIC` or `REPLAY` origin → quality gate →
verified session policy → `MultiEngineRunner` → external ABI parser
or ordinary public engine → validated `SignalIntent` with **PAPER** evidence
→ `PaperJournal` on SQLite.

The journal uses atomic batches, idempotent hashes, conflict rollback and
restart persistence. It is intentionally separate from the A3
`SignalLedger` / Telegram outbox: no fake live attestation, no
`FORWARD` evidence and no send attempts.

Negative tests cover disabled-by-default state, stale or duplicated quote,
unverified session, engine-fault isolation, schema/version mismatch,
wrong market/provider/time/engine, nonfinite and floating-point prices,
invalid risk geometry, extra or duplicate JSON fields, oversized payloads,
cross-restart durability, conflicting signal IDs, and rejection of live
quotes.

## Preserved boundaries and remaining work

- The public `Multi-Market-Trading` repository never imports private
  `NY-First-Reversal` source. The private GitHub repository stays private.
- No existing historical `production_source`, v0.3.2 manifest,
  `Dockerfile.production`, Compose identity/volume, or v0.4.0rc1 package
  release metadata is modified.
- The generic offline runner and journal cannot prove edge, real performance,
  licensed engine access, authenticated market feeds or true Telegram
  exactly-once delivery.
- Later production integration requires separate owner authorization,
  signed or otherwise verifiable plugin custody, entitlement checks,
  authenticated quote sources, actual end-to-end preflight, and explicit
  deployment approval.

**A7 is complete only when its dedicated tests and all existing required
GitHub security/publication/legacy regression checks pass.**
