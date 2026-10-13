# Universal artifact acceptance — phase 1 (no execution)

**Status: proposal / nonproduction source capability.** The registry covers
all 15 file extensions requested, but **does not execute any strategy**. It
inspects supplied in-memory bytes and returns a SHA-256-pinned,
deny-by-default `ArtifactInspection`. No source is written or extracted, no
runtime is selected, no uploaded source is installed, and no Telegram/broker
permission exists.

## Recognized formats and exact boundaries

| File | Purpose | V1 checks | Actual runtime still required |
|---|---|---|---|
| `.py` | Python 3.12 strategy source | SDK AST/static lint; ≤64KiB | reviewed Python worker / certified Core API adapter |
| `.json` | declarations or data | strict JSON UTF-8, duplicate-key denial | exact manifest schema or data adapter |
| `.zip` | canonical SDK source bundle ONLY | existing deterministic two-member SDK inspector | independently certified isolated Python worker |
| `.csv` | historic price data | UTF-8, header, row-width validation | Point-in-Time OHLCV/tick mapping + provenance |
| `.parquet` | historic price data | `PAR1` envelope/footer plausibility ONLY | vetted Parquet decoder + schema/timezone verification |
| `.js` | JavaScript strategy source | UTF-8 validation ONLY | isolated JS runtime + exact CoreResult ABI |
| `.ts` | TypeScript strategy source | UTF-8 validation ONLY | reviewed compiler/build + isolated JS runtime |
| `.mq4` | MetaTrader 4 source | UTF-8 validation ONLY | independently provisioned MT4 terminal/bridge |
| `.mq5` | MetaTrader 5 source | UTF-8 validation ONLY | independently provisioned MT5 terminal/bridge |
| `.ex5` | compiled MT5 strategy | opaque binary recognition ONLY | matching authorized MT5 terminal; native execution restricted |
| `.pine` | TradingView Pine source | UTF-8 validation ONLY | semantics-preserving source port plus independent tests; no native arbitrary Pine execution |
| `.dll` | native Windows library | PE magic check ONLY | isolated Windows worker with audited ABI and bitness |
| `.so` | Linux shared library | ELF magic check ONLY | isolated Linux worker with audited ABI |
| `.exe` | native Windows executable | PE magic check ONLY | isolated Windows worker with restricted transport |
| `.wasm` | WebAssembly binary | wasm v1 magic/version ONLY | pinned Wasmtime-compatible sandbox, fuel/memory/time limits, ABI tests |

Caveats: Valid magic bytes do **not** prove executable format integrity,
authorship, licensing, no malware, deterministic behavior or trading-edge
quality. In particular `.ex5` is proprietary and cannot be reliably validated
without an appropriate MetaTrader environment. Pine is TradingView-specific,
and reimplementing its semantics requires independent equivalence evidence.
Some historical `.mq4/.mq5` files use non-UTF-8 encodings; V1 refuses them
until a reviewed transcoding step is designed.

## Policy and data flow

`raw bytes + safe filename -> bounded inspection -> digest + proposed adapter`

Every result is `UNTRUSTED_ARTIFACT_REVIEW_REQUIRED`, with
`executable=adapter_installed=market_data_authenticated=paper_enabled=
live_enabled=telegram_enabled=False`. Future runners must independently
enforce provenance, publisher trust, compiler/terminal compatibility, license,
reproducible packaging, no-secret/no-network isolation, resource limits,
per-core identity, host-owned settings, Risk Manager and strict Core API
validation. No `extension` or metadata flag can grant execution or switch
PAPER into FORWARD.

`inspect_artifact` accepts byte buffers only and has an 8 MiB maximum
artifact size. The limits and UTF-8 requirements are **phase-1 inspection
limits**, not a promise to ingest arbitrarily large datasets or compiled
programs. For larger archives and datasets, use a separate streaming loader
and verified read-only storage.

**Important:** `.csv` content is untrusted and must be escaped before any
spreadsheet export. `.parquet` is not decoded here. A successful initial
inspection cannot serve as a quality-controlled trading data source.

This additive component **does not change** Al Brooks, NYFR R0,
First Follow-up, Public Custom Engine, private strategy source, current
adapter-free PAPER runtime, existing public/legacy contracts, live services
or any server. It intentionally introduces **zero execution capability**.

## Follow-up implementation stages (not yet completed)

1. Build safe streaming CSV/Parquet adapters with exact market-identity,
   candle-completeness, quote semantics, gap and Point-in-Time checks.
2. Build certified isolated `.js/.ts/.wasm` runners using a stable
   versioned JSON CoreResult adapter and adversarial conformance tests.
3. Build broker-owned MT4/MT5 bridge for `.mq4/.mq5/.ex5`, with
   binary compatibility, signed trust and paper-only shadow execution.
4. Design strictly contained native runner for `.dll/.so/.exe`—never
   load untrusted code into the bot process.
5. Establish a Pine-specific port/equivalence workflow (no false promise
   of drop-in native Pine compilation).
6. End-to-end PAPER admission, conformance certification, developer
   permissions and restart/recovery; then a separate forward/live review.

### Validation

`python -m pytest -q tests/unit/test_universal_artifact_intake_v1.py`

Tests check 15 accepted extensions, structure checks, adversarial bad
filenames and malformed files, noncanonical ZIP/path traversal refusal,
zero-authority results, source limits, and no execution grants.
