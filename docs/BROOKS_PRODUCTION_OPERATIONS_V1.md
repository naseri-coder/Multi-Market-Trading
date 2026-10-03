# Brooks Production Operations v1

This update completes the operational layer around Brooks Full Core v3 without
adding exchange order execution.

## Automatic signal lifecycle

Only Brooks `LIVE` / `VIP` signals created after `BROOKS_OPS_CUTOVER_AT` are
automatically tracked. Closed 1-minute candles are used so no unclosed-candle
lookahead is introduced.

Lifecycle:

`WAITING_ENTRY -> ENTRY_ACTIVATED -> TARGET_HIT / STOP_HIT -> CLOSED`

If the order of entry/stop/target cannot be known inside the same 1-minute
candle, the signal is marked `OUTCOME_AMBIGUOUS`, cancelled, and excluded from
win-rate outcome events. This is intentionally fail-closed.

Signal P/L is a versioned engineering model: leveraged percentage return with
equal allocation across targets. It does not include exchange fees, funding,
slippage, or actual fills and is not exchange-execution P/L.

## Telegram lifecycle update

The worker edits the original `TELEGRAM_VIP` message caption after entry,
targets, stop, close, or ambiguity. Failed edits remain pending in durable state
and are retried.

## Win rate

No new win-rate formula is introduced. The existing analytics source of truth
remains `signal_events`, where the latest `TARGET_HIT` or `STOP_HIT` outcome for
each eligible signal is counted. Because the lifecycle worker now writes those
events automatically, rolling win-rate becomes automatic for new LIVE signals.

## VIP subscription entitlement

Active subscriptions are reconciled with the configured VIP channel. Active
subscribers who are not members receive a one-user expiring invite link by DM.
Expired subscribers previously managed by the worker are removed. Outstanding
managed invite links are revoked on membership or expiry. Administrators/owners
are never automatically removed.

## Payment settlement

The existing payment model remains gateway-independent. A successful payment
created/finalized after the operations cutover is automatically converted into a
subscription. If the user already has an active subscription, settlement is
deferred and retried periodically so remaining subscription time is not lost.

No external payment company is selected by this update. The included
`payment_mark_success.sh` / `payment_mark_failed.sh` scripts provide a safe
MANUAL provider path now. A real gateway can later call the same PaymentService
success/failure transition without changing entitlement logic.

## Monitoring and backup

`runtime_health` stores durable heartbeats for:
- `signal_lifecycle`
- `payment_settlement`
- `vip_entitlement`

`scripts/ops_status.sh` prints current operational state. A root cron entry runs
a PostgreSQL logical backup daily and retains 14 days.

## Explicit exclusions

- No exchange API key is required.
- No exchange order is created, amended, or cancelled.
- Public-channel auto publication remains disabled.
- No replay, holdout, or backtest is run by the installer.
