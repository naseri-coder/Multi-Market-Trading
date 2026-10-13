# Stage 21B — Captured public-format KuCoin Futures -> causal offline PAPER

**Status:** opt-in, nonproduction, research-only. Not independently verified exchange data, correct real futures PnL, live orders, real Telegram, or release authorization.

## Purpose and reviewed boundaries

Stage 21A captures a strictly bounded complete OHLC dataset with raw SHA256, operator-specific symbol and timeframe, and labels it REPLAY. Stage 21B takes **operator-provided raw official-format response bytes**, the exact `FuturesKlineRequest` for each dataset and a Stage-6 public metadata `ProviderSnapshot`. It **does not make network calls**. Both raw sources are independently unverified. It refuses missing/partial candles, stale or time-forward metadata, mixed symbols, production environment, missing operator acknowledgment or reuse of an existing state directory.

The exact Stage-6 instrument identity, selected host bindings and a single illustrative, reviewed `OfflineContractFixture` travel through Stage 12 panel -> Stage 5 REPLAY Core API -> Stage 17 durable job -> Stage 16 REPLAY bridge -> Stage 19 pre-call intents -> Stage 8 risk -> Stage 9 PAPER -> Stage 10 optional no-send outbox -> Stage 13/19 read-only forensic verification. Stage 16/17/19 now support an **explicit** `data_origin=DataOrigin.REPLAY` argument; the old default remains `SYNTHETIC`.

## Causality and modeling

- Scan every observed candle chronologically with a trusted Core API evaluator; choose the **first** eligible setup with a subsequent full candle. Never choose the best realized-PnL outcome.
- Use a **limit-at-decision-price** hypothetical entry for the *next* bar only. If the price was not touched, cancel the simulated order. If that entry bar also touched stop/target, classify `INTRABAR_UNRESOLVED` and cancel the hypothetical order, **not** as a win, successful fill, or evidence of no real-world loss. This intentionally discards an ambiguous candidate rather than inventing fill ordering.
- A modeled limit touch uncontaminated by same-entry-bar stop/target can be filled at the strategy's entry price. Exits are modeled only on **later** complete bars, using the existing Stage-9 stop-before-target conservative ambiguity and configured toy fees/slippage.
- A position remaining open at end is honestly marked open, never forcibly closed or counted as a realized result. Modeled realized PnL excludes unrealized valuation.
- Two distinct KuCoin Futures symbols/timeframes use one controlled PAPER account. No signal-send / no actual broker route. No self-retry after crash. Restart reconciliation verifies local database continuity; Stage 19 intents cover initial reserve/plan/no-send effects, not later PAPER fills or exits.
- Exact response SHA256 is *integrity of local bytes*, not an exchange-authenticated signature.

## Economic limitations

Stage-6 public metadata does **not** currently certify KuCoin futures contract multiplier, position unit semantics or minimum lot size. Stage-21B account capital, quantity step and contract multiplier are **explicit toy PAPER assumptions**; performance is displayed as `modeled_realized_net`, not actual KuCoin PnL, actual contract PnL or proven strategy edge. Symbol listings do not certify region, account permissions or residency eligibility. Pseudo quantity is research-only.

## Use by trusted Python caller

The API is `run_captured_paper_pilot(destination, datasets=((query1, raw1), (query2, raw2)), provider_snapshot=stage6_snapshot, observed_at=utc_capture_time, operator_ack=True)`. The caller prepares both exact Stage-21A official-format API responses as immutable bytes and an independently inspected Stage-6 public contract metadata snapshot. The function accepts only a **new** owner-private state directory; all other paths are refused. The tested built-in default has `quantity=Decimal('0.001')` and optional `dry_run_signals=False`. It performs **no HTTP or API calls**. Do not label an injected/offline fixture `LIVE`.

The mandatory CI workflow tests causal replay across two symbols and two timeframes, Stage-19 exact intent counts, local offline risk journal, no-fill cancellation, ambiguous entry-bar non-scoring, no-setup, no-send signal independence, restart and fail-closed state/environment gates; also verifies the installed wheel from outside the repository.

## Manually executable installed-wheel CLI (no network)

`python -m naseri_markets.captured_paper_cli_stage21b_v1` reads three **preexisting** owner-private JSON files: one exact Stage-6 KuCoin public contract snapshot and two independent official-format Kline response bodies. Every supplied file must be a regular non-symlink 0600 file in an owner-only directory, and the output directory must not already exist.

```sh
MMT_NONPRODUCTION=1 python -m naseri_markets.captured_paper_cli_stage21b_v1 \
  --state-dir /absolute/private/new-stage21b \
  --metadata-json /absolute/private/kucoin-contracts.json \
  --metadata-asof 2026-10-12T10:00:00Z \
  --capture-observed-at 2026-10-12T12:00:00Z \
  --first-symbol XBTUSDTM --first-timeframe 15m \
  --first-start 2026-10-12T10:00:00Z --first-end 2026-10-12T11:00:00Z \
  --first-json /absolute/private/xbt-4-bars.json \
  --second-symbol ETHUSDTM --second-timeframe 5m \
  --second-start 2026-10-12T10:00:00Z --second-end 2026-10-12T10:20:00Z \
  --second-json /absolute/private/eth-4-bars.json \
  --ack-offline-captured-paper
```

These timestamps/filenames are merely examples; the raw bodies must exactly match the specified windows and genuine operation requires a separately reviewed historical metadata as-of date. The command makes **zero** network calls; Stage 21A's probe command prints only a provenance digest summary, not the raw bytes, so the operator must supply local raw JSON captures separately. Even if raw bytes came from a public provider, they are **not independently attested** by this stage. `--no-dry-run-signals` disables signal journaling but leaves PAPER enabled. CLI tests assert missing acknowledgment, file-symlink refusal, exact dual-asset end-to-end completion and independently installed package execution.

## Still blocked / next acceptance

- This stage does not authenticate a live Telegram panel session or publicly certify the true Al Brooks strategy adapter. The only executable strategy in this candidate is the reviewed example core.
- A qualified provider metadata and contract multiplier service, independently verified real public capture, rate-limit/licensing/residency review and sample-size evidence are required before authentic multi-market PAPER confidence.
- Production and public release stay `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE`.
- Do not change private NY First-Reversal, production bot, v0.3.2 legacy runtime, main server, Telegram or broker credentials.

**No-setup outcome:** if the entire scan finds no eligible entry, the Stage-13 gate correctly returns `BLOCKED` (`NO_EVALUATED_OUTPUT_EVIDENCE`) and the Stage-19 exact-effect inspection is **not applicable**. This is a valid lack of trading signal, **not** a successful end-to-end journal attestation. Do not insert dummy effects to force a PASS.
