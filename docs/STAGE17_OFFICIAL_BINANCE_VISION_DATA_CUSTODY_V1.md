# Stage 17 — Official USD-M Historical Data Capture, Custody & Local Quality Gate

**Status: CAPTURE PATH IMPLEMENTED; NO REAL DATASET ACQUIRED IN THIS EXECUTION (NETWORK BLOCKED)**

Research-only; never production, trading, publishing, live signals or a backtest.
Parent: main@9a438195d41f1934f918a8a42c290c359c48924f (merged Stage16, PR #299).

## Exact bounded scope

- Binance Vision official **USD-M futures trade-price klines** only. Not spot, mark prices, order book quotes, funding or settlement history.
- BTCUSDT linear perpetual, 15m bars, one *closed complete UTC month*. One fixed official URL for ZIP and sibling .CHECKSUM.
- Python trusted system TLS; strict 200/exact requested URL; refuse redirects, unexpected encodings, oversized bodies and other origins. 20s per-request timeout.
- Reuse existing Stage16 full archive validation: complete calendar month, 12 columns, exact candle timing, OHLC and volume, archive SHA-256 and named checksum line, safe decompression. Produce DATA-A1 canonical CSV and Stage12 receipt.
- Store original ZIP and checksum, canonical CSV and receipt in a new private research directory. Run the **actual existing Stage12 full-file** quality and locally consistent as-of audit before writing the final JSON acceptance report.
- **No modifications** to frozen Brooks source, thresholds, SHA256SUMS, release manifests, any operational database, Telegram, servers, paper orders, live trading, private NYFR or main.

## Provenance trust boundary

1. HTTPS endpoint retrieval is an observed transport event if the operator's trusted TLS session succeeds. It is **not** independent exchange-signed data or a trusted external timestamp.
2. The sibling .CHECKSUM is a SHA-256 consistency value **published by the same endpoint**, not a cryptographic publisher signature. The publisher may revise archives later. Separately preapproved hashes for both artifacts freeze a selected revision but do not create a signature.
3. The Stage16/Stage12 gates certify local integrity, month continuity and local as-of consistency. They do **not** verify independently signed origin, absence of historic revisions, independent custody clock, executable bid/ask, actual fill probabilities, funding/mark completeness, liquidations or a profitable strategy.
4. Stage17 executes **no backtest**. Stage18 economics, Stage19 Brooks backtest, Stage20 OOS/Walk-Forward and Stage21 Forward/PAPER require separate authorization.

## Operator procedure — isolated nonproduction machine

Use Python 3.12 in a clone of this repository with its dependencies installed. The destination must be a fresh absolute path whose parent already exists; it must not be a symlink or contain a production_source/.git/secrets/checkpoints component.

    export MMT_NONPRODUCTION=1
    export MMT_PRODUCTION=0
    python -m naseri_markets.stage17_official_archive_capture_v1 \
      --year 2024 --month 1 \
      --destination /tmp/stage17-btcusdt-2024-01-research-capture \
      --ack-nonproduction

The directory is created mode 0700 and individual files mode 0600; files are not committed to GitHub. Before inspecting price performance, record the chosen month and applicable data usage terms. This example month is not a claim that acquisition succeeded.

For **two preapproved version pins obtained independently of the current fetch**, additionally pass:

    --zip-sha256 PREAPPROVED_SHA256_64_HEX \
    --checksum-sha256 PREAPPROVED_SHA256_64_HEX

Both pins are required together or both omitted. Without them the report explicitly indicates a self-observed checksum only. The approval source/time must be recorded out-of-band; deriving those hashes from the same download is not independent approval.

## Acceptance gate

- Explicit nonproduction opt-in **before network**, whole month already closed, hard bounded body sizes.
- Exactly two required public URLs, no redirects, no secrets or authenticated broker APIs.
- Raw official-format ZIP + sibling checksum validation, optional exact preapproved pair.
- Complete month's canonical CSV verified again by actual Stage12 audit; retained raw inputs and deterministic SHA lineage.
- Independent authentication, trusted external clock, historic revision absence, mark/funding/orderbook verification, OOS, profitability and LIVE authorization remain **false**.
- Offline tests use mocked transport and generated synthetic prices; tests never prove an archive was genuinely obtained. CI never downloads from the market.

## Execution blocker observed

Attempted official checksum URL:
https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-2024-01.zip.CHECKSUM

This research environment could not resolve the official archive host; no actual archive/checksum bytes were acquired. There is therefore **no real dataset hash or real-month quality report yet**.

**Final empirical evidence state: BLOCKED_OFFICIAL_ARCHIVE_UNREACHABLE**, not Stage17 real-data acceptance. Run only from a permitted separate research machine or validate genuine archive inputs when provided. Do not relabel a synthetic fixture as authentic history.
