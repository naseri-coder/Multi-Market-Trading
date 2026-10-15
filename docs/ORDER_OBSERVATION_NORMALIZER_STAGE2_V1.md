# Order Observation Normalizer V1 — Stage 2

**NONPRODUCTION / PAPER-RESEARCH ONLY.** This is an additive pure library. It does not connect to a provider, process real broker orders, post transactions, infer realized PnL, retry, cancel, publish Telegram messages, update the database, or change the existing Stage 3/8/9 order/position lifecycle.

## Purpose and alignment

The existing \`naseri_markets.execution_contract_v1.OrderStatus\` remains the **single canonical status enum**. The new \`naseri_markets.order_observation_normalizer_v1\` interprets a bounded subset of native status labels from an **explicitly named provider**, assesses a separately supplied **cumulative quantity observation**, and returns an immutable \`ObservationDecision\`.

This is **not** a second execution engine. The module never books the difference between cumulative quantities as an exchange fill. Stage 3's per-fill execution IDs, fee currencies, prices, contract multipliers, authoritative execution receipts and economic reconciliation remain out of scope.

## Deterministic behavior

1. **Explicit provenance** — Require supported provider name, order identity, event identity, aware timestamp and finite \`Decimal\` cumulative quantity. Unknown provider status is \`quarantined\`, not interpreted as canceled or filled.
2. **Order identity** — The observation must match both the checkpoint provider and order ID; no cross-order merging.
3. **Monotone evidence** — An event with timestamp earlier than **or equal** to a different accepted event, or cumulative filled quantity lower than the previous quantity, is quarantined.
4. **Quantity/status consistency** — \`ACKNOWLEDGED\` and \`REJECTED\` require zero fill; \`PARTIALLY_FILLED\` requires strictly partial quantity; \`FILLED\` requires exactly the requested quantity; canceled orders may contain a partial fill.
5. **Terminal fence** — Subsequent new event IDs cannot re-open or mutate a terminal order. Conflicts require independent reconciliation, not optimistic replay.
6. **Idempotence with limitations** — Caller supplies a bounded, immutable history of (event ID, evidence SHA-256). Exact repeated event+semantics is \`duplicate\`; same ID with different semantics is quarantined. Capacity 256 causes refusal to advance. This is **not** globally durable exactly-once: caller owns atomic storage, checkpoint authenticity, deduplicated provider event IDs, and any long-lived history strategy.
7. **No execution authority** — The output exposes only \`applied\`, \`duplicate\` or \`quarantined\`, with a stable reason enum and the proposed immutable checkpoint. Neither \`applied\` nor a terminal status implies order settlement or a green light for automated action.

Provider mapping intentionally excludes ambiguously documented or conditional states, including Binance \`PENDING_CANCEL\`, Bybit \`Untriggered\` / \`Triggered\` and unsupported Bitget statuses. Normalization accepts exact case-insensitive vendor tokens only; no substring guesswork.

## Offline example

\`\`\`python
from datetime import UTC, datetime
from decimal import Decimal

from naseri_markets.order_observation_normalizer_v1 import (
    OrderObservation, OrderProgress, assess_order_observation,
)

current = OrderProgress(
    venue="okx", order_id="paper-order-1", requested_quantity=Decimal("2")
)
observation = OrderObservation(
    venue="okx", order_id="paper-order-1", event_id="fixture-event-1",
    native_status="partially_filled", cumulative_filled=Decimal("0.5"),
    occurred_at=datetime(2026, 10, 15, tzinfo=UTC),
)
decision = assess_order_observation(current, observation)
assert decision.verdict == "applied"
assert decision.progress.cumulative_filled == Decimal("0.5")
assert current.cumulative_filled == Decimal("0")
\`\`\`

## References for evidence review

- [Binance spot order-status enums](https://github.com/binance/binance-spot-api-docs/blob/master/enums.md)
- [OKX order status and partial IOC cancellations](https://www.okx.com/docs-v5/en/)
- [Bybit V5 order history and asynchronous updates](https://bybit-exchange.github.io/docs/v5/order/order-list)

The mappings are a **bounded research subset**, not an exhaustive live exchange contract; venue API families, position modes and status schema versions must be reviewed independently before any adapter integration. Provider assertions are not authenticated by this library.

## Acceptance / release limits

- Unit tests cover known and unknown statuses, direct fill, partial fill, partial cancel, event-ID collisions, duplicate replay, out-of-order messages, cumulative regression, cross-order confusion, inconsistent terminal statuses, invalid Decimals/timestamps, receipt exhaustion and immutable outputs.
- No code from an external project is copied; this is a newly implemented component using existing internal contracts.
- No changes to legacy sources, manifest digests, config, database schema, risk policy, Docker, deployment, secrets, provider clients or public signal publication.
- Deliberate **NO-WIRING** boundary: the module cannot influence real orders or PAPER order persistence until a separately approved integration stage.
