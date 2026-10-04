# FM Core Foundation

This document freezes the infrastructure boundary for the second signal core.

## Current state

The first core remains the Al Brooks core and keeps its own runtime, historical
probability, cold-start lifecycle, and strategy route.

The second strategy is registered as `FM`. Its Telegram channel, enabled state,
and engine readiness are stored independently in `signal_strategy_configs`.

The FM trading engine itself is intentionally **not implemented yet**.

## FM connection contract

A future FM core must implement `app.modules.fm_runtime.contracts.FMEngine`:

- a stable `engine_id`;
- an explicit `engine_version`;
- asynchronous `start(FMRuntimeContext)`;
- asynchronous `shutdown()`.

The application-level `FMRuntimeCoordinator` owns connection/disconnection to
the configured FM route. The default FM engine registry is empty, therefore the
system synchronizes `engine_ready=false` and fails closed until an actual FM
implementation is registered.

When an engine is registered, the coordinator reconciles the FM strategy route
independently. Enabling/disabling FM or changing its channel starts/stops or
rebinds only the FM engine.

## Isolation invariants

The FM runtime package must not import:

- `brooks_core` or `brooks_core_v3`;
- `brooks_runtime`;
- Brooks Historical Probability or cold-start contracts;
- Brooks production operations or scale-in state.

Shared infrastructure may include the database manager, Telegram transport, and
generic signal/strategy routing. Strategy-specific decision logic and evidence
remain owned by the respective core.

The FM route cannot become effective unless all three conditions are true:

1. the admin selected FM as enabled;
2. an FM private channel is configured;
3. an actual FM engine is registered and therefore `engine_ready=true`.

## Persistence boundary

Migration `20261004_0022` reserves `producer='FM'` in automation metadata and
creates independent strategy routing configuration. The future FM integration
must always persist producer identity as `FM`; it must never write FM evidence
under `producer='BROOKS'`.

Any FM-specific statistical or lifecycle tables should use FM-owned names or a
strategy discriminator with explicit isolation tests.

## Delivery boundary

The FM engine receives a `TelegramStrategyVipPublisher` already bound to the
configured FM channel. It must not read the Brooks channel ID or reuse Brooks
strategy configuration.

## Safety boundary

This foundation does not implement FM analysis, does not create FM signals, does
not enable LIVE exchange execution, and does not authorize real trading.

Building the FM core is a separate stage. That stage should add the engine
implementation, its own tests/research evidence, and explicit registration at
the application composition root.
