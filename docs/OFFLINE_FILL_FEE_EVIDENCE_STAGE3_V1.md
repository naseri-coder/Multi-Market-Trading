# Stage 3 — Offline Execution Fill & Fee Evidence V1

**Scope:** Nonproduction, pure, independent module in `naseri_markets/offline_fill_evidence_stage3_v1.py`. This is a **read-only fixture interpreter**, **not** an exchange connector or transaction ledger. No live credentials, API calls, order submission, order retries/cancel, database writes, signal sending, trading strategy import, or PnL settlement.

## Why another contract?

Existing `execution_contract_v1.OrderStatus` and Stage 2 `order_observation_normalizer_v1` already handle **order-level status and cumulative filled quantity**. Stage 3 interprets a **per-execution** fill record. It does **not** reuse status/cumulative updates as actual fills, and is not a replacement for Stage 3/8/9 PAPER position accounting.

Per-execution evidence includes explicit `account_scope`, venue, market family, provider-native symbol, order ID, fill ID, side, positive `Decimal` fill quantity/price, **unit** (base units versus swap contracts), exact UTC fill time, optional maker flag, and fee evidence.

| Fixture schema (explicit) | Channel / market | Quantity semantics | Fee interpretation |
| --- | --- | --- | --- |
| Binance USD-M | `ORDER_TRADE_UPDATE`, inner `x=TRADE` | BASE | Nonnegative `n` charge with currency `N`; absent / zero-without-currency is `PENDING` |
| OKX | private `orders`, `instType=SWAP` | CONTRACTS, **not** base asset | Per-execution `fillFee`: negative = charge, positive = rebate; `fee` (cumulative) is **never** used |
| Bybit | `execution.linear`, `category=linear`, `execType=Trade` | BASE | Per-execution `execFee` plus independently denominated optional `extraFees`; no unverified rebate inference |
| Bitget UTA | `arg.instType=UTA`, `arg.topic=fill`, `category=usdt-futures` | BASE | `feeDetail` components; no cross-asset summing |

Provider-format acceptance is limited to these four schemas; **no other market unit, user account mode, subscription channel or provider status is guessed**. Unrecognized and ambiguous payloads raise `FillRefused` with a fixed non-sensitive code.

## Security and accounting acceptance rules

1. Caller explicitly supplies expected **order ID, symbol and account scope**. Every row must match; no cross-order/account aggregation. Caller-supplied scope is a **label**, not authentication or proof of ownership.
2. No floats, scientific notation, NaN, Infinity, boolean-to-number coercion or generated timestamps. Decimal strings are bounded and parsed without rounding. Native milliseconds are converted to UTC **without floating-point timestamp conversion**.
3. Batch size is limited to 16. Duplicate fill IDs or any malformed row **reject the entire batch**, never silently drop bad entries while accepting the rest.
4. Fees are **per-fill** and preserve **both currency and direction**. Different fee currencies must never be added together. Missing fees remain `PENDING` and are **not** represented as zero. A fee amount without its currency is rejected.
5. An immutable result omits raw payloads and provider response text. Secret-bearing unexpected input fields are not copied into the output or into thrown exceptions.
6. `fill_evidence_digest` supports semantic identity comparisons; `compare_fill_evidence` reports `DISTINCT`, `DUPLICATE` or `CONFLICT` for the same scoped fill ID. It **does not** make a durable or concurrency-safe exactly-once guarantee. Atomic storage and downstream recovery require separate work.
7. All emitted records are **unverified fixture observations**, not authenticated broker receipts. They **do not** book transactions, update realized PnL, determine margin, establish final fees, or authorize a trading action. Unknown fees and conflicting repeated fills must be independently reconciled before any accounting.

## Minimal offline demonstration

```python
from naseri_markets.offline_fill_evidence_stage3_v1 import (
    parse_offline_execution_fixtures,
)

fixture = {
    "e": "ORDER_TRADE_UPDATE",
    "o": {
        "x": "TRADE", "s": "BTCUSDT", "i": 123, "t": 9001,
        "S": "BUY", "l": "0.25", "L": "100.125",
        "z": "0.25", "q": "2", "T": 1750000000123,
        "n": "0.0015", "N": "USDT", "m": False,
    },
}
fills = parse_offline_execution_fixtures(
    "binance", fixture,
    account_scope="paper-account",
    expected_symbol="BTCUSDT",
    expected_order_id="123",
)
assert len(fills) == 1
assert fills[0].quantity_unit == "base_units"
assert fills[0].fee_state == "observed"
```

## Official format evidence (read-only reference)

- [Binance futures order trade update schema](https://developers.binance.com/en/docs/products/derivatives-trading-coin-futures/user-data-streams) — USD-M implementation must be reviewed independently before any authenticated integration.
- [OKX private orders and fills semantics](https://www.okx.com/docs-v5/en/)
- [Bybit V5 private execution schema](https://bybit-exchange.github.io/docs/v5/websocket/private/execution)
- [Bitget UTA private fill schema](https://www.bitget.com/docs/uta/websocket/private/Fill-Channel)

## Deliberate exclusions and evidence gate

Only three new files in this stage: module, unit tests and this document. No source/config/release/manifest changes elsewhere, no startup wiring, no database/Telegram/provider integration, no server usage and no production changes. The source is independently authored and contains no external-project branding.

Acceptance requires source-quality verification, malicious/malformed payload refusal tests, precise fee/time/quantity checks, and all required GitHub PR safety gates. A later stage may separately propose a **reviewed bridge** between authenticated provider receipts, this observational format and the existing PAPER ledger; that bridge is **not** implemented or authorized here.
