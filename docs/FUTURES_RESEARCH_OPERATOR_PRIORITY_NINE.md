# Operator futures exchange research priority — 2026-10-11

This is the **operator's requested fixed investigation order**, NOT
CoinMarketCap's exchange rank or a verified order of 24-hour futures
trading volume. Source for real exchange volumes is
[CoinMarketCap derivatives](https://coinmarketcap.com/rankings/exchanges/derivatives/);
its composite exchange score, reported 24h volume and open interest are
three different metrics and cannot be conflated.

The **Iran-resident futures-eligible exchange allowlist stays EMPTY**:
official exchange restrictions or missing affirmative residency permission
mean no runtime selection, no Kraken/Binance fallback, no PAPER signals,
no Telegram channel publication and no broker orders. The public-research
priority view must never produce an `ex:set` or `ep:set` callback.

| Operator priority | Research venue | Official futures/API evidence | Iran-resident futures |
| --- | --- | --- | --- |
| 1 | Binance Futures | [USD-M API](https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info) | Officially restricted; no product activation |
| 2 | Bybit | [V5 derivatives API](https://bybit-exchange.github.io/docs/v5/intro) | Officially restricted; no product activation |
| 3 | MEXC | [Futures REST/WS API](https://www.mexc.io/api-docs/futures/integration-guide) | Officially restricted; no product activation |
| 4 | LBank | [Contracts API](https://www.lbank.com/en-US/docs/contract.html) | Officially restricted; no product activation |
| 5 | XT.COM | [USDT-M/Coin-M API](https://doc.xt.com/docs/futures/Access%20Description/BasicInformationOfTheInterface) | Unverified; no product activation |
| 6 | Toobit | [USDT-M market API](https://api-docs.toobit.com/api/usdt-m-market-data) | Official terms restrict high-risk FATF jurisdictions; no activation |
| 7 | Bitunix | [Futures API](https://www.bitunix.com/api-docs/futures/common/introduction.html) | Iran explicitly prohibited; no activation |
| 8 | BigONE | [Contract API](https://open.big.one/docs/contract/introduction/) | **Unverified** for Iran: general [BigONE agreement](https://bigone.zendesk.com/hc/en-us/articles/115001990533-BigONE-User-Agreement) and [Eurasia agreement](https://bigone.zendesk.com/hc/en-us/articles/20997939628441-BigONE-Eurasia-User-Agreement) impose jurisdictional constraints; neither establishes Iranian-resident derivatives authorization |
| 9 | KCEX | [Official futures product](https://www.kcex.com/en-us/support/articles/30088664472729) confirmed, but authoritative API developer documentation NOT independently verified | Official restriction; no activation |

## Where the user sees it

- Private Telegram: `/engines` → Brooks → Settings →
  **🔎 اولویت پژوهش صرافی‌ها (۹ مورد)**, paginated 5+4.
  Every row is only text. Page navigation and Settings return are the
  only buttons; no selection/mutation/control callbacks exist.
- Isolated development CLI (Stage 1 installed preview):
  `mmt-dev venues` outputs machine-readable fixed priorities, evidence
  URLs, restriction status and `orders_enabled=false` with no network.
- The older 20-entry futures catalog is retained as historical research,
  not the Iranian-resident selectable list. BigONE is NEW only in the
  read-only research priority shortlist; it is not a verified market
  adapter or default exchange for any engine.

## Volume verification nuance

A snapshot of the latest CoinMarketCap derivatives leaderboard showed
Binance and Bybit among major ranked exchanges, while reported 24h volume
for MEXC was marginally above Bybit at observation time. Therefore the
user's requested priority cannot truthfully be presented as a sorted
volume ranking. CoinMarketCap did not provide a comparable BigONE
derivatives volume/rank in the visible ranked snapshot. No volume numbers
are stored in this feature and no unsubstantiated live rank is invented.

When provider permission is affirmed with official current terms, a
separate approval plus verified official futures instrument metadata,
frozen engine integration and safety tests is required. This change
does NOT alter exchange/position permission policy or bypass
regional/identity restrictions.

No legacy `production_source`, `SHA256SUMS`, private NYFR, VPS,
PostgreSQL, Telegram publication or production Docker files touched.
