# Brooks Futures — exchange-scoped pair selection (nonproduction)

Research date: 2026-10-10. This is a **PAPER-only** feature. It does
not trade, publish Telegram signals, grant futures trading permission to
Iranian users, use API keys or access production hosts.

## What a selection actually does

Private Telegram manager: `/engines` → **Al Brooks Price Action** →
**⚙️ Settings** → **💱 انتخاب جفت‌ارز فیوچرز**. Tap one of the
exchange-specific pairs; the saved `futures_symbol` persists in the
operator-private SQLite database. All clicks are admin-only, versioned
(CAS), audited and fenced against stale inline callbacks.

For **Kraken Futures**, the following documented **linear USD perpetual**
identifiers can be selected, not symbols from Binance USDT markets:

| Display symbol | Contract | Quote | Execution |
|---|---|---|---|
| `PF_XBTUSD` | BTC/USD perpetual | USD | Public PAPER feed with historical CI network E2E |
| `PF_ETHUSD` | ETH/USD perpetual | USD | Documented instrument; metadata + closed-candle validation at runtime, mock-data frozen V5 E2E |
| `PF_SOLUSD` | SOL/USD perpetual | USD | Documented instrument; metadata + closed-candle validation at runtime, mock-data frozen V5 E2E |

Sources:
- [Kraken officially published USD perpetual contract specifications](https://support.kraken.com/articles/4844359082772-linear-multi-collateral-derivatives-contract-specifications)
- [Kraken public trade candle API](https://docs.kraken.com/api/docs/futures-api/charts/candles)
- [Kraken derivatives Iran restriction](https://support.kraken.com/articles/360023786632-kraken-derivatives-eligibility)

There are also six common **UNVERIFIED candidates** (BTCUSDT,
ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, ADAUSDT) offered for each of the
remaining 19 catalog venues. These are **not assertions of currently
listed/open trading contracts**, and no signals can be issued for
catalog-only venues. They must undergo provider-native instrument
verification and complete PAPER integration before any runtime use.

Selecting another exchange atomically resets `futures_symbol` to that
exchange's safe default: Kraken → PF_XBTUSD, others → BTCUSDT.
The old saved timeframe, enablement and settings revision persist
through the additive SQLite migration. Wrong-exchange or wrong-symbol
requests are refused even before HTTPS; Kraken V5 replay rechecks the
same identity **inside the atomic journaling transaction** so a
mid-flight pair change cannot record a signal using stale settings.
No automatic fallback to Kraken if another venue was selected.

On each Kraken request the **public instrument metadata**, including
tradeable status and price tick size, must independently match the
exact selected symbol; no hardcoded uniform tick across assets. Finalized
continuous closed candles are checked against the selected timeframe.
The SHA-frozen Brooks V5 engine is executed without modifying the
legacy tree, strategy thresholds or private NY First-Reversal code.

**Status caveat:** BTC Kraken has already passed a genuine outside
network E2E via GitHub Actions. ETH and SOL are documented real
contracts with offline genuine-engine fixtures, but must still pass
fresh live public network E2E from the target runner before claiming
end-to-end production-like connectivity. Even successfully evaluating
a market does not imply a tradeable or profitable signal.

The [Bitunix restricted-region notice](https://www.bitunix.com/fr-fr/hub/helpcenter/article/bitunix-restricted-regions-and-user-eligibility-notice?id=146)
explicitly restricts Iran; the 20-venue catalog reflects this. Other
unverified exchanges must not be represented as unrestricted. Do not
circumvent KYC, prohibited countries, access restrictions or exchange
Terms of Service.

**Zero live deployment**: no signal channel sends, no trades, no
production DB writes, no server startup/restart.
