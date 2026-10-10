# Brooks Futures — twenty venue candidates and eight verified candle intervals

Date of desk research: **2026-10-10**. This is a public NONPRODUCTION PAPER feature.
The catalog has **20 futures/derivatives venues**, selected from
[CoinMarketCap derivatives-market listings](https://coinmarketcap.com/rankings/exchanges/derivatives/),
not twenty verified Iranian-approved trading venues.

## Source and eligibility policy

The official Kraken derivatives eligibility policy explicitly lists **Iran
as restricted**:
https://support.kraken.com/articles/360023786632-kraken-derivatives-eligibility

WEEX's official terms also list **Iran** as excluded:
https://www.weex.com/help/articles/4417379529241

CoinEx stated in June 2026 that it introduced **geo-fencing/access
restrictions for Iranian regions**:
https://www.coinex.com/en/blog/14875-coinex-official-statement-regarding-the-wall-street-journal-report

All other listed venues have **UNVERIFIED** Iranian eligibility in this
version, not "available", "sanctions-free" or "no KYC". Individual product,
residence, account, location and policy conditions can differ and change
without warning. Public price-feed availability is **not** authorization
to create a trading account or trade derivatives. Do not bypass geo-fencing,
identity verification, restricted regions or exchange terms. Do not use
a VPN as a means to evade exchange restrictions.

The exact immutable venue identifiers and labels are in
`naseri_markets/futures_venues.py`, in this order:

1. Kraken Futures (Iran explicitly restricted, public PAPER feed verified)
2. Binance Futures (real runner HTTP 451; cannot claim reachable)
3. OKX
4. Bybit
5. Gate
6. Bitget
7. MEXC
8. KuCoin
9. BingX
10. XT.COM
11. HTX
12. LBank
13. Toobit
14. Bitunix
15. WEEX (Iran explicitly restricted)
16. BloFin
17. Phemex
18. KCEX
19. CoinEx (official Iran geo-fencing)
20. BTCC

Items 3–20 (except where restriction information is listed) are
**CATALOG_ONLY**. No new private APIs, derivatives permissions or contract
mapping are asserted for them. Kraken has independently verified public
`PF_XBTUSD` USD perpetual market candles and metadata, and a real pinned
Brooks V5 PAPER end-to-end smoke. The Binance USD-M adapter is present but
**HTTP_BLOCKED** from the tested GitHub runner (HTTP 451), so the catalog
does not activate it for the standalone worker. Its distinct `BTCUSDT`
USDT-quoted price source must never be aliased to Kraken BTC/USD.

## Eight selected timeframes

The `/engines` → Brooks → Settings panel now has an **explicit
eight-button selector**:

| Label | ID | Period seconds |
| --- | --- | ---: |
| ۱ دقیقه | `1m` | 60 |
| ۵ دقیقه | `5m` | 300 |
| ۱۵ دقیقه | `15m` | 900 |
| ۳۰ دقیقه | `30m` | 1800 |
| ۱ ساعت | `1h` | 3600 |
| ۴ ساعت | `4h` | 14400 |
| ۱۲ ساعت | `12h` | 43200 |
| روزانه | `1d` | 86400 |

Kraken's [official Charts API](https://docs.kraken.com/api/docs/futures-api/charts/candles)
documents all eight as supported trade-candle resolutions. The shared
PAPER replay parser requires 60–256 fully closed continuous bars at the
selected period with UTC time alignment; the Kraken adapter requires
fresh closed data and maintains the precise source, symbol and tick
metadata. Timeframe settings are versioned and CAS-checked again after
network and immediately before journal commit. Changing period cannot
retroactively convert already persisted signals or duplicate scans.

## Per-engine private Telegram panel

`/engines` → Brooks → Settings → **🏦 انتخاب صرافی فیوچرز (۲۰ مورد)**
displays 4 pages of 5 venues. ⛔ indicates explicit Iran restriction,
⚪ indicates unverified, 🧪 a verified public PAPER feed. The admin
can save a venue preference, including catalog-only; this is **not**
the same as switching on data acquisition. Preference changes persist
with CAS revision/audit and protect against stale inline-button replies.
The private panel also offers **⏱ انتخاب تایم‌فریم** with all eight
explicit buttons. These settings belong to Brooks; they do not expose
or change private NY First-Reversal source or a public Custom engine.

## Exact dispatch contract, no fake cross-venue signal

When the separately operator-started `naseri-brooks-paper-service` is
alive **and** Brooks is enabled, signal_environment = PAPER,
market_scope = crypto/all, selected exchange = **kraken**,
the service fetches Kraken Futures for the selected timeframe, invokes
the authentic SHA-frozen Brooks V5 engine, and durably records PAPER
signal intents only when real eligibility/geometry holds. No profit or
frequency is promised: a cycle may yield NO_SIGNAL.

If the user selects any other exchange, it remains saved and shown in
the panel, but the current standalone worker returns
`BROOKS_SELECTED_EXCHANGE_FEED_NOT_READY`, with **zero external market
requests and no signal**. That explicit failure is safer than silently
printing Kraken results under an unsupported exchange brand. Direct
Kraken/Binance pollers also reject before HTTP unless the exact
exchange identity is selected.

Requests to publish to a channel remain non-effective, even after
Brooks is turned ON: **Telegram publication, LIVE trade execution,
production bot restarts and server deployment are still disabled**.
Future work can onboard each additional venue individually only after
authoritative contract APIs, instrument identity, availability,
geographical eligibility, closed-candle freshness, exchange tick
metadata, full V5 tests and independent PAPER evidence. No regional
restrictions may be bypassed.
