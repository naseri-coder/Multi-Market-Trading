# Product Stage 2 — futures eligibility vs PUBLIC metadata (2026-10-11)

**Implemented:** a single Iran-resident futures eligibility decision in
`naseri_markets/iran_futures_eligibility.py`, enforced for all *new*
Kraken/Binance PAPER poll requests, private Telegram exchange+pair selection,
the underlying SQLite settings writer and standalone supervisor. Historical
settings already in the development SQLite remain READABLE for audit, not
selectable. Pure OFFLINE replay, and separate public market metadata
research, do not constitute account access or licensed trading.

## Two distinctly different paths

| Path | Authorized capability | Never grants |
| --- | --- | --- |
| **Public futures contract metadata** | Public GET of Kraken/KuCoin official `instruments` / `contracts/active` JSON; offline parsing/research | Residency eligibility, broker login, live orders, PAPER signal issuance, automatic Telegram delivery |
| **Iran-resident product** | Admin-only list of positively verified venues and (eventually) validated derivative pairs | Automatic permission from public HTTP response, volume ranking, simulated tests, fake KYC or proxy |
| **Frozen V5 offline fixtures** | Separate nonproduction, SHA-pinned OHLCV replay tests | Any right to trade in a restricted venue or publish live-channel signals |

The approved residency venue list remains **EMPTY** (not a claim that
every exchange worldwide is restricted). The code intentionally returns
no exchange choices and continues to stop Brooks production-facing PAPER
analysis until affirmative exchange proof exists.

## Real official exchange contract list APIs

The new research parser uses exchange-native exact symbol identifiers,
not a fabricated list of `BTCUSDT` variants:

- **Kraken Futures:** official public
  [REST host](https://support.kraken.com/articles/360022839491-api-urls-derivatives),
  `GET https://futures.kraken.com/derivatives/api/v3/instruments`.
  Includes `PF_XBTUSD`, `PF_ETHUSD` and other
  `PF_...USD` linear USD perpetual symbols; the parsed snapshot keeps
  the exchange-returned tick size and `tradeable` flag. The flag is
  about exchange contract status **only**, not Iranian customer eligibility.
  [Kraken derivatives eligibility](https://support.kraken.com/articles/360023786632-kraken-derivatives-eligibility)
  prohibits Iran residents.
- **KuCoin Futures:** official
  [Get All Symbols (public)](https://www.kucoin.com/en-au/docs-new/rest/futures-trading/market-data/get-all-symbols),
  `GET https://api-futures.kucoin.com/api/v1/contracts/active`.
  It returns native identifiers such as `XBTUSDTM`, separate
  `quoteCurrency`, `status`, `tickSize` and expiration.
  Expiring contracts are excluded from the perpetual-only researcher.
  Resident futures availability for Iran is **UNVERIFIED**.

Only these two published, fixed HTTPS hostnames are supported in this
phase. A response size cap, no redirects, no proxies, strict JSON schema,
unique symbols/keys, positive tick size, timeout and row limits are
enforced. Malformed or unavailable APIs fail closed. No API key, trading
endpoint, direct orders or arbitrary supplied URL is accepted. All
selected contracts are **observational research metadata**.

### Running a real public contract listing

On a **separately authorized, isolated development host**, after the Stage 1
installer and `export MMT_NONPRODUCTION=1`:

```bash
"$HOME/mmt-product-dev/mmt-dev" contracts \
  --venue kraken --max-results 100 \
  --ack-public-metadata-research

"$HOME/mmt-product-dev/mmt-dev" contracts \
  --venue kucoin --max-results 100 \
  --ack-public-metadata-research
```

The output contains exact public contract symbols, status, quote currency,
tick size, source URL, contract count, pagination-truncation marker and
explicit `account_trading_authorized=false`,
`paper_signal_generation_authorized=false`,
`telegram_publication_authorized=false` and
`iran_resident_futures_approved=false`. It is NOT persisted as tradeable
symbols in the SQLite settings store. HTTP 403/451/rate limits and unavailable
endpoints are reported as refusal; no geographic/KYC circumvention.

**Verification boundary:** GitHub CI parses strict representative bytes
from official API response schemas and verifies the installed wheel. This
proves native contract mapping and fail-closed research plumbing. A successful
live pull of the latest contract list from an actual target host has **not
been verified in this stage's CI**; no live-volume, count or exact up-to-date
listing is invented. Run the explicit commands above only where allowed.

## Unified fail-closed controls

- **Core SQLite**: `change_preference` now refuses changing the
  `futures_exchange` or `futures_symbol` to a venue without positive,
  current Iranian-resident derivatives eligibility, *even when called
  directly and not via the Telegram menu*. CAS, audit, unchanged-history
  and stored old selections remain protected.
- **Direct public-data-to-PAPER pollers**: both Kraken and Binance
  `poll_once` refuse before any metadata/candle HTTP call, then repeat
  the approval gate after the network response and before V5 replay/PAPER
  journal. Source symbol and selected exchange must match saved settings.
  The only exception is **independent, no-signal, read-only metadata
  research** through the command above.
- **Standalone worker and health / Telegram panel**: reuse the same
  `resident_paper_feed_ready` predicate (venue approval + feed + pair).
  A stale legacy stored venue cannot silently become enabled.
- **New approvals**: require official *affirmative* Iranian-resident
  futures trading permission, reliable contract API documentation and
  verified integration, plus ongoing eligibility review. A public
  `tradeable=true` market record does not prove account availability.
- **No production changes**: no VPS, Docker Compose, legacy code/source
  SHA256SUMS, private NY First-Reversal, Telegram sends or live trading.

## Outstanding stage 3 work

Real API discovery is now a separate research command. It is **not yet a
production-grade dynamic symbol selection UI**; such a feature would need a
validated cache/versioning, periodical official API refresh, symbol delisting
race checks, independently verified residency trading permission and
provider-specific OHLCV integration. With no positively approved venues,
promoting any found Kraken/KuCoin symbol into the Iran-resident panel
would be misleading, so this stage intentionally does not do so.
