# Iran-resident futures exchange eligibility audit — 2026-10-11

**Result: ZERO international venues passed all three mandatory proofs**:
1. Published, affirmative and current eligibility for **Iran-resident users specifically to trade futures**.
2. Live derivatives/futures market with contract terms.
3. Published usable futures market-data API with independently valid contract symbols.

Therefore the `/engines` → Brooks → futures exchange selector shows **no verified exchanges**, not misleading endorsements. No exchange from the former 20-entry public UI remains selectable. Prior chosen preferences are preserved only as historical metadata in the operator-private development database, with a visible restriction warning. The standalone development worker refuses to generate new PAPER signal records from a restricted or unverified venue. Old direct Kraken public-data V5 test harnesses remain for nonproduction validation, isolated from the Iran-facing menu. No LIVE trading, Telegram sends or deployment.

## Decision register

| Exchange(s) | Decision and primary evidence |
| --- | --- |
| Binance | Excluded: Iran is explicitly excluded from service; [official release](https://www.binance.com/en-IN/square/post/07-17-2026-binance-will-list-aerodrome-aero-with-spot-trading-pairs-345629600310082) |
| OKX | Excluded: [official risk and compliance disclosure](https://www.okx.com/en-us/help/risk-compliance-disclosure) |
| Bybit | Excluded: [official excluded locations](https://www.bybit.com/en/promo/campaign/trader-house) |
| Gate | Excluded: [official user agreement](https://www.gate.com/docs/Gate-User-Agreement.html) |
| Bitget | Excluded: [official terms](https://www.bitget.com/en-CA/support/articles/360014944032-terms-of-use) |
| MEXC | Excluded: [2026 official restricted-country statement](https://www.mexc.com/terms) |
| BingX | Excluded: [official platform disclaimer](https://bingx.com/en/support/articles/360034028153-0) |
| HTX | Excluded: [official user agreement](https://www.htx.com/support/ru-ru/detail/360000112261) |
| Kraken Futures | Excluded: [official derivatives eligibility](https://support.kraken.com/articles/360023786632-kraken-derivatives-eligibility) |
| LBank | Excluded: [official access limitations](https://www.lbank.com/support/articles/21436496711705/) |
| Toobit | Excluded pending explicit confirmation: [official terms](https://www.toobit.com/en-US/support/toobit-terms-of-use) refuse high-risk FATF jurisdictions; [FATF June 2026](https://www.fatf-gafi.org/en/publications/High-risk-and-other-monitored-jurisdictions/call-for-action-june-2026.html) identifies Iran as a countermeasures jurisdiction. Offers [official futures API](https://api-docs.toobit.com/api/usdt-m-market-data), but this does **not** prove Iranian eligibility. |
| Bitunix | Excluded: [2026 restricted-regions notice](https://www.bitunix.com/fr-fr/hub/helpcenter/article/bitunix-restricted-regions-and-user-eligibility-notice?id=146) |
| WEEX | Excluded: [official restricted regions](https://www.weex.com/help/articles/4417379529241) |
| BloFin | Excluded: [official terms](https://v3.blofin.com/en/support/Terms/7296238795279-TERMS-OF-USE) |
| Phemex | Excluded: [official terms](https://phemex.com/help-center/phemex-terms-of-use) |
| KCEX | Excluded: [official agreement](https://www.kcex.io/en-US/support/articles/23962442522649) |
| CoinEx | Excluded: [official Iran geo-fencing statement](https://www.coinex.com/en/blog/14875-coinex-official-statement-regarding-the-wall-street-journal-report) |
| KuCoin | No current affirmative futures service assurance for Iran; [Sep 29 2026 terms](https://www.kucoin.com/legal/terms-of-use) include sanctions and geographic controls. Status: NOT VERIFIED. |
| XT.COM | No affirmative current futures eligibility proof for Iran; [official website](https://www.xt.com/app) and terms/access limitations need verified review. Status: NOT VERIFIED. |
| BTCC | No affirmative general Iranian futures eligibility; [official copy-futures article](https://www.btcc.com/en-CA/academy/btcc-guide/what-is-copy-trading-how-to-start-copy-trading-on-btcc-a-beginners-guide) excludes Iran for that futures service. Status: NOT VERIFIED. |

Further venues (e.g. Pionex, Tapbit, BitMart, Deribit, CoinW) also explicitly reject Iranian users in their official terms; they are **not** replacements.

### Volume ranking

Data source: [CoinMarketCap derivatives exchanges](https://coinmarketcap.com/rankings/exchanges/derivatives/), with **reported 24-hour derivatives USD trading volume** as the sorting metric, not the site's composite exchange rank, spot volume or open interest. Volume changes continuously and is not evidence of Iranian trading authorization.

As an illustrative research-only snapshot of currently **unverified** candidates, XT.COM had approximately USD 4.17 billion in 24h derivatives volume and KuCoin USD 1.46 billion on the queried source, so descending volume would put XT.COM ahead of KuCoin; **neither is on the approved list**. BTCC had no reliable comparable 24h figure in the inspected page; no rank is fabricated.

Approved ranking is currently an **empty list**, not a meaningless ranking of restricted venues. The code exposes `ranked_iran_futures_venues()`, which orders only proof-qualified candidates by comparable 24h USD volume. A new entry requires an up-to-date **affirmative eligibility policy for Iranian residents**, product-level futures evidence and official API documentation; merely being absent from a restricted-country list is not approval.

### No invented capability

The historical, unmodified Kraken public price feed and authentic Brooks V5 testing may still be used for source-code regression, but cannot be selected in the resident-eligible exchange picker or used by the standalone PAPER service under the default real eligibility policy. The UI's eight timeframe selectors remain, and future chosen venue/pair contracts remain versioned, source-checked, and fail closed.

This is a defensible *zero-result* assessment, not a claim that all global derivatives exchanges ban Iran. Regional terms change, and the user must obtain direct, documented operator permission before a venue can be promoted from research to production-ready candidate. Never circumvent KYC, regional blocks or exchange Terms of Service.
