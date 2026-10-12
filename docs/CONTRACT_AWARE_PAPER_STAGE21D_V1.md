# Stage 21D — Per-instrument immutable futures economics in PAPER

**Status: nonproduction only.** This applies public KuCoin-format contract multiplier, lot/quantity step, tick-size and taker fee parameters to PAPER accounting. It **does not** verify actual broker/exchange fills, venue costs, actual leverage margin, funding, liquidation, mark-price drift, account access, exchange signatures or strategy profitability.

## Authoritative basis

- KuCoin public Get Symbol documents `multiplier`, `lotSize`, `tickSize`, `takerFeeRate`, `makerFeeRate`, `settleCurrency`, `isInverse` and `isQuanto`: https://www.kucoin.com/docs-new/rest/futures-trading/market-data/get-symbol
- KuCoin realized PnL for USDT-margined contracts: signed (exit - entry) × number of contracts × multiplier, less trading and funding fees: https://www.kucoin.com/support/26695061760793
- Stage21C's forward-armed contract snapshot remains public **unattested** material; no retroactive metadata substitution.

## Changes, fail-closed defaults and compatibility

`PaperContractEconomics` is immutable and binds `provider=kucoin_futures`, native symbol, USDT settlement, `LINEAR_USDT_PERPETUAL`, positive `contract_multiplier`, integral contract `quantity_step`, `price_tick`, maker/taker rates, operator-research slippage, exact metadata SHA256 and explicit source mode. Unsupported inverse, coin-margin, unknown/zero size, missing settlement, or invalid rates are refused. Prices must fit contract tick and order quantities the discrete lot step.

The Stage3 risk ledger now has **opt-in per-instrument** and **per-order frozen** records in the same SQLite connection. Economics selection occurs before reservation; the order-specific snapshot is inserted **atomically** with the risk reservation and later cannot change merely because a new market metadata response appears. Stage8 instance risk and notional budget checks use the exact same model as Stage3. Stage3 daily-loss circuit-breaker and Stage9 fills/exits, partial target lot quantization, per-order realized net and realized R consume the immutable **order snapshot**, not a mutable global account multiplier. The absence of a Stage21D policy leaves **all old Stage3/8/9 semantics unchanged**.

For `Q` contracts, multiplier `m`, `E` entry, `S` initial stop, `X` exit, conservative taker fee rate `f` both sides, worst slippage fraction `s`:

- `notional = Q × m × E` in USDT.
- `reserved risk = Q × m × (abs(E − S) + E × f + max(E,S) × (f + s))`.
- `gross = sign × (X − E) × Q × m`, with sign +1 long, -1 short.
- `modeled costs = Q × m × (E × f + X × f + max(E,X) × s)`; `net = gross − modeled costs`.
- `net realized R = net / (filled contracts × abs(E − initial stop) × multiplier)`; excludes unrealized PnL.

These are **research assumptions** and not a KuCoin accounting replica: no true execution, fees tier, funding charges, interest, liquidation, actual commission/mark price, slippage realization, balances or contract changes between snapshots.

`run_captured_paper_pilot(..., contract_economics=(policy1,policy2), quantity=Decimal('1'))` opts into Stage21D, requiring exactly two symbol-bound immutable records with exact Stage6 public metadata SHA256. No-candidate conditions remain `BLOCKED` for the Stage13 attestation. Real candle bytes remain `DataOrigin.REPLAY`, never `SYNTHETIC` or `LIVE`. `replay_sealed_bundle` now opts in by default and passes the two separately frozen contract economics records; CLI adds `--contracts N` (native **contracts**, not base-coin units), where N must respect **both** instrument lot steps. If different lot steps cannot support a common N, the operation is refused before creating the PAPER state; per-symbol quantity allocation requires a later review.

A **separate read-only Stage21D audit** checks each reservation's instrument, metadata SHA256 policy digest, modeled notional/risk and each stored Stage9 exit's gross, fee and net. It also reconciles totals with Stage21B output and preserves Stage13 and Stage19 operational checks. The new report states `MODELED_PER_INSTRUMENT_APPLIED_UNATTESTED`; `real_exchange_contract_pnl_verified` and `profitability_proven` remain **false**.

## Evidence

PR CI validates distinct symbol multipliers and fees, long/short formulas, discrete contract lots, unsupported instrument rejection, tampered exit receipt rejection, nonproduction fences, complete Stage19/20/21B/21C relevant regression and clean 3.12 installed-wheel acceptance. **No CI network traffic to the exchange**. Any actual public research ARM and SEAL requires a separate authorized operator action in a nonproduction workstation; nothing automatically contacts KuCoin, Telegram or brokers.

## Next open risks

The Stage3 initial margin cap still uses an operator-selected account-level leverage ceiling, not exchange-calculated liquidation price or full futures margin tiers. No venue order book, real historical funding, position transfer, liquidation price simulation, fill probability, maker queue priority, spread, region permission or actual capital is verified. Stage21D is contract-aware **modeled PAPER**, not live trading readiness. The public Al Brooks Core API is still not certified and NY First-Reversal private source is unchanged. Remain `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE`.

All existing production server, bot, telegram, private-core and legacy runtime paths remain unchanged.
