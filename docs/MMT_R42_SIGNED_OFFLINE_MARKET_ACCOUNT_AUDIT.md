# R42 — Signed OFFLINE market capture + dual account consistency audit

**Status (2026-10-16): developed, locally synthetic-tested, Draft.**
It is NOT provider authentication, actual account reconciliation, live venue
eligibility, release authorization, or a connected PAPER/broker integration.

## Why this is a new bounded check

Stage5's OfflineMarketDataEngine accepts explicit REPLAY/SYNTHETIC data,
and Stage6's ResearchInstrumentCatalog is research metadata with
trading_authorized=false. Stage3 AccountRiskPolicy explicitly disclaims
external authenticated equity/exposure. R42 supplies an *independent
read-only evidence validation boundary*, not a replacement for these
existing modules, and does not import or activate their runtime engines.

File: scripts/mmt_r42_signed_market_account_audit_v1.py

The operator separately pins SHA256 of a canonical 1-version local research
policy, and independently pins both the complete canonical snapshot
SHA256 and DER SubjectPublicKeyInfo (SPKI) SHA256 fingerprints for three
*distinct* Ed25519 public keys.

The three roles (with distinct domain separators) are:
- FEED: offline capture of a closed candle, bid/ask, price tick, venue,
  contract/instrument id, symbol, timeframe, sequence and UTC timestamps;
- ACCOUNT_PRIMARY: local offline primary capture of equity, gross
  exposure, sorted open-order and position IDs and sequence;
- ACCOUNT_REVIEW: separately encoded local offline review capture of
  exactly the same account/equity/order/position state.

Each record and policy must be **canonical exact-field JSON** (compact
UTF-8, sorted keys, ASCII-escaped, one newline, no duplicate JSON keys).
Files are read without following symlinks, bounded by 8 KiB per JSON and
4 KiB per public key, requiring one hardlink and ordinary regular files.
Signatures are detached raw 64-byte Ed25519; role-separated signature input
is literal: MMT-R42-<ROLE>-V1 followed by a newline and the JSON bytes.
The script never creates a keypair or performs signing.

## Strict financial and causality checks

- Nonproduction only: MMT_NONPRODUCTION=1 and **no** MMT_PRODUCTION
  environment variable of any value; caller must provide an explicit
  timezone-aware UTC instant (the trusted time is not inferred from records).
- The exact policy purpose is OFFLINE_RESEARCH_ONLY with both
  session_status and region_status **UNVERIFIED_FOR_TRADING**.
  No venue/market/account trading eligibility can become true.
- Exact venue, market, contract/instrument identifier, symbol,
  timeframe and account/currency identities must match.
- Feed sequence and both account sequences must meet independently
  pinned minimum floors; a persistent sequence ledger for live replay
  protection is NOT implemented.
- The candle open-to-close interval must equal the configured
  timeframe; open precedes close, which precedes capture and the
  trusted current time. Time freshness, maximum feed latency, account
  capture freshness and pairwise account↔feed skew are bounded.
- Decimal values are parsed *only from strict positive/nonnegative
  finite decimal strings*, never floats. OHLC inequalities, bid <= ask,
  spread in basis points, price tick divisibility and explicitly
  trapped Decimal InvalidOperation reject malformed/overprecision feeds.
- The primary/reviewer account capture comparison enforces equality of
  sorted unique open-order and position IDs, matching snapshot
  sequences, and bounded equity/gross-exposure differences. The
  reviewer cannot promote unknown balances into live cleared exposure.

A success-shaped result is strictly:

    R42_SIGNED_OFFLINE_CAPTURES_CONSISTENT_RELEASE_DENIED

Its positive claims are limited to cryptographic signature verification
of **the three supplied keys** and internal consistency checks of
**the supplied offline records**. The result permanently says
real_provider_provenance_verified=false,
real_account_reconciliation_verified=false,
venue_session_and_region_eligible=false,
broker_order_authorized=false, telegram_authorized=false,
live_authorized=false, public_release_authorized=false and
files_written=false.

## Actual independent local test evidence

Executed in an assistant disposable container with:
- Python 3.13.5
- pytest 9.0.2
- cryptography 46.0.4
- PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, PYTHONDONTWRITEBYTECODE=1;
  pytest -c /dev/null --noconftest -p no:cacheprovider;
- **45 PASSED in 0.23 seconds**, in-memory/temporary synthetic
  account and market files, using ephemeral throwaway Ed25519 keys.

The main GitHub source byte identity was independently confirmed
using the exact Git Blob SHA-1. The locally executed script's Git Blob
is 635a299de44968207ae71259411b1ac90d8c42ee and matches the
GitHub script blob exactly. The GitHub test source was formatted
slightly differently from the local test fixture; therefore the
statement "45 PASSED" is strictly about the locally executed synthetic
harness against the **byte-identical implementation**, not a
GitHub Actions run or an operator Python 3.12 acceptance.

Negative cases cover all three wrong pins/forged signatures/missing
signatures, reused key fingerprint, stale/future/replayed feed,
expired/forged policy, wrong venue/timeframe, wrong volume semantics,
trading eligibility, high spread and tick violation, account time skew,
wrong equity/gross exposure/order/position IDs and sequences, malformed
signed numeric values, duplicate JSON keys and account IDs,
symlinks and any explicit MMT_PRODUCTION flag, and oversized
Decimal precision arithmetic. No real-market symbol data or
broker accounts were accessed.

## Remaining Stage15 P0 blockers — NOT CLOSED

P0_AUTHENTIC_MULTI_MARKET_FEEDS:
- Obtain authorized actual provider/feed adapter and authenticated
  exchange/broker contract identifier, market/session and region/account
  trading eligibility. Independent TLS/API custody, trusted server
  timestamps, sequence and integrity logs and disconnected feed response
  must be independently reviewed.
- Prove actual Stage5/Stage6 feed adapter acceptance/recovery and
  sessions and data quality using reproducible nonproduction evidence.

P0_ACCOUNT_RECONCILIATION:
- Independently authenticated account/equity/margin/remote order state
  and **per-position detailed signed positions**, not only ID sets.
  A separate trusted dual source and auditable sequencing/cursor
  custody is needed. This new R42 schema does not include detailed
  quantity, fill or reservation reconciliation.
- Match remote state against actual internal risk ledger, including
  unknown orders, pending fills, collateral, currency conversion,
  negative equity and stale/mismatched snapshots; install an approved
  kill switch and manual reconciliation before any broker command.
- An independent test host, real provider sandbox consent,
  secrets and operator identity review remain prerequisites. Nothing
  here alters the Stage3 or Stage15 live-authorization gates.

The tool is not enabled by default in the product runtime, does not
write files, never instantiates client connections and cannot grant
public, live, Telegram or production permission. R27 Brooks still
DEFERRED and Stage15 retains nine P0 and one P1 outstanding blockers.
No main merge, user Termux, operational Telmivo host or GitHub Actions
workflow was used.
