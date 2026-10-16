# Stage17 Network-Independent Binance Vision Archive Intake

**Implementation mode: nonproduction. A network-free ingest path exists, but a genuine archive is not yet present in the current execution environment.**

Stage17's existing HTTPS downloader refuses if the official archive host cannot be reached. That DNS failure must not be "fixed" by disabling TLS, accepting third-party mirror data as authentic, or fabricating candles.

## Safer fallback: operator-supplied original bytes

An operator can independently obtain an **official Binance Vision BTCUSDT USD-M futures 15m full closed-month ZIP and its sibling `.CHECKSUM`** using a personally controlled, permitted machine. Both original files must be retained byte-for-byte in the same isolated directory, named exactly like:

- `BTCUSDT-15m-2024-01.zip`
- `BTCUSDT-15m-2024-01.zip.CHECKSUM`

Primary source format documentation: https://github.com/binance/binance-public-data

Then on a **separate research-only Python 3.12 environment**, with no operational bot, database or Telegram credentials:

```python
from pathlib import Path
from naseri_markets.stage17_official_archive_capture_v1 import (
    import_stage17_vision_month_offline, persist_research_capture,
)

capture = import_stage17_vision_month_offline(
    Path("/isolated/input/BTCUSDT-15m-2024-01.zip"),
    Path("/isolated/input/BTCUSDT-15m-2024-01.zip.CHECKSUM"),
    year=2024, month=1, operator_ack=True,
    # Optional, supplied as a pair *if approved before this import*:
    # expected_zip_sha256="...64-character SHA-256...",
    # expected_checksum_sha256="...64-character SHA-256...",
)
report = persist_research_capture(
    capture, destination=Path("/isolated/output/stage17-btcusdt-2024-01"),
)
```

Set `MMT_NONPRODUCTION=1` and `MMT_PRODUCTION=0` first. Destination must be a **new, private, absolute directory**, and parent must exist. The importer has **no network calls** and refuses missing acknowledgement, symlink/nonregular files, over-sized input, wrong filenames and bad hashes. It reuses the exact Stage16 monthly parser, full 12-column OHLCV and time-grid checks, Stage12 file-based PIT quality checks and immutable SHA lineage.

A SHA calculated from locally obtained files shows only integrity relative to those files. The companion CHECKSUM is not a signature and an operator's local import timestamp is not a provider-signed acquisition timestamp. The output continues to report **source_independently_authenticated=false**, **retrieval_clock_independently_attested=false**, and **historical_revision_absence_proven=false**. Only independent custody or publisher-authentic evidence can improve these statements; do not relabel an internal receipt as exchange-certified.

## Empirical acceptance blockers still open

1. We do **not currently have authentic ZIP/CHECKSUM bytes**, so the importer has only been tested with **synthetic complete-month fixtures**.
2. Stage18 operator-asserted funding/mark schedule is **not proven** as the whole historical settlement inventory; effective fee account tier, bid/ask and order book slippage, historical contract size/tick and tiered liquidation are unverified.
3. Stage15/19 report decision hashes, not validated original fill prices, entry-stop-target execution, order lifecycle or net realized-PnL. Do not convert LONG or SHORT decisions directly into executed trades.
4. Stage20's retrospective stored month cannot be a pristine prospective holdout. Hashing it at present does not backdate a precommitment.
5. GitHub publication checks require a true **CodeQL** check from GitHub Advanced Security; creating a normal test with the same name or changing the required security checker app would be an impermissible bypass.

**Stage21 must remain blocked** until data, economics, trade lifecycle, OOS protocol and protected CI are independently accepted. The offline fallback only removes the need to download from Binance *on the research evaluator itself*.

## How to provide data for the next acceptance pass

Upload the two actual original files as conversation attachments; do not provide exchange API credentials or private signing keys. They can be inspected as data, not executed, then validated with the new importer in a sealed research workspace. The source of acquisition, date/time and original official URL should be supplied separately so provenance can be evaluated honestly.
