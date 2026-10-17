# DATA-A1 → RUNTIME-A1 → PAPER: integration and safety review (2026-10-14)

Baseline: main 0cec0e6f53777ffd28c8d12f3cf9e588b3001804. This is a source-contract review, not an integration test or runtime certification.

## Verified source facts

- DATA-A1 `naseri_markets/historical_data_loader_a1.py` reads operator-approved digest-pinned CSV/Parquet, validates typed replay MarketPackets, and never executes a strategy. A real provider file has not been authenticated.
- RUNTIME-A1 `naseri_markets/multilang_runtime_a1.py` admits only synthetic/replay CoreInput and exact source SHA256. All four language routes default to WORKER_NOT_INSTALLED.
- RUNTIME-A2 implements an experimental four-language Worker and fixed harmless fixtures, not a production or hostile-code sandbox. Its candidate Dockerfile uses a mutable base tag and package downloads; no signed/reproducible worker image is certified.
- RUNTIME-A3 has an opt-in SQLite durable lease/quarantine wrapper; it is not automatic release/recovery.
- RUNTIME-A6 `require_worker_launch` is an unconditional denial before A1 daemon probing or process spawn and is also invoked inside `_run_oci`. It must remain unchanged.

## Explicit integration gap

A DATA-A1 MarketPacket is **not** an A1 CoreInput and cannot be fed directly into `MultiLanguageOfflineHost.evaluate`. An authorized future adapter must use the existing market-data and Core API validation contracts to bind the same symbol/timeframe/source, enforce event availability and point-in-time closed-candle semantics, and produce a deterministic, read-only PAPER observation. No adapter, execution grant, or bridge to broker/Telegram is created by this review.

## Acceptance before further work

1. Define and test packet-to-CoreInput identity, replay timing, deduplication and quality-failure behavior with fixed harmless fixtures, **without** calling A1 Worker execution.
2. Test that a replay result cannot trigger live/forward, broker, Telegram, or external order paths.
3. Preserve A6 unconditional deny; add regression tests for direct and indirect Worker entrypoints.
4. Separately verify rootless/gVisor confinement and immutable signed OCI provenance on a designated disposable host before proposing any launch authority.
5. Obtain an actual operator-approved historical CSV/Parquet file before making provider quality or profitability claims.

**Verdict:** DATA_A1_RUNTIME_A1_CONTRACT_REVIEWED__PAPER_ADAPTER_NOT_IMPLEMENTED__EXECUTION_DENIED.
