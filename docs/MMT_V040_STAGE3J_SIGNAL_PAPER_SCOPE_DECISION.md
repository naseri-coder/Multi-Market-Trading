# Stage 3J — Product-owner freeze: SIGNAL_ONLY + PAPER, retain existing LIVE code unchanged

**Owner decision, October 2026:** Multi-Market-Trading stays open source under the existing Apache-2.0 license for now. The project remains **one first-party extensible multi-market bot/platform**, accepting owner- and customer-supplied cores and indicators through approved interfaces. This release must make **SIGNAL_ONLY** and **PAPER** correct and independently reviewable.

## Explicit LIVE preservation

If LIVE modules already exist, **leave all their source, interfaces, current behavior and implementation unchanged**. Do NOT delete, rename, truncate, rewrite, enable, deploy or develop LIVE in v0.4.0. New LIVE development is **reserved for a future version**. No automatic orders are authorized by this document or by a green CI. Existing controls and access restrictions remain applicable. The isolated Stage3J test branch requires unchanged Git subtrees for `naseri_markets`, `production_source` and `platform_release`; it changes only this decision record, a CI file, and test cases.

## v0.4.0 behavioral acceptance (independently verified versus remaining blockers)

| Lane | Mandatory acceptance | Existing proof level |
| --- | --- | --- |
| SIGNAL_ONLY | Approved core identity and selected user route; engine evaluation produces a versioned signal; durable signal outbox, idempotency and recovery; no PAPER order, no LIVE order | Offline synthetic first-party integration and mocked transport tests exist. Actual Telegram delivery for independent customers and real custom-core onboarding are **NOT verified**. |
| PAPER | Selected custom/built-in core, instrument and tenant policy; separately enabled paper ledger, independent risk caps; simulated order state transitions, fill/SL/TP, fees where modelled, PnL, restart/dedup; NO broker order, NO actual Telegram send | Offline synthetic Core API and PAPER tests exist. Customer user-supplied isolated custom core, broker contract parity, and real market-feed integration are **NOT verified**. |
| LIVE | Remain exactly as implemented today; not a v0.4.0 acceptance or development lane | NOT authorized or release-tested here; Binance 451 and Bybit 403 public provider integration failures remain unresolved. |

## Stage3J scoped test-only branch

`ci/stage3j-signal-paper-scope-20261018` starts at original green candidate `7bbb3541fb6d63f960bee9f197fe026ed6d04608`. New unit regression cases probe signal-only registration, storage, duplicate suppression and zero simulated orders; paper-only independent simulated risk/order receipt with no signal delivery; analysis-only inertness; and fail-closed production environment without ledger mutation. Existing first-party signal/outbox, public-bot fake-transport, PAPER lifecycle and integrated restart tests are run together in a **Linux network namespace with no network**. This is not equivalent to a multi-tenant user-custom-core end-to-end system or actual Telegram delivery.

**Not sufficient for sign-off:** a green offline test suite does NOT by itself satisfy customer-provided untrusted core isolation, live-to-production user signal delivery, actual external market-data access or all v0.4.0 product UX. Release remains blocked until specific acceptance proofs and authentic human/trust review; no automatic change to PR #352 or official version tags.

Stage3H/3I two-entrypoint demonstration Wheels remain experimental evidence, not replacement of the nine-entrypoint platform. Keep PR #352 draft, protected main untouched, no official tag, production/Telmivo, real Telegram sends or LIVE orders.
