# R42 — Pinned offline synthetic feed and account evidence (NO release)

Date: 2026-10-16. Status: source verified and assistant-local
synthetic tests passed; real provider/account acceptance PENDING.

## Scope and existing behavior

Existing Stage5 market data engine accepts only REPLAY/SYNTHETIC events,
already detects sequence gaps, future/late timestamps and wrong
contracts. Existing Stage3 account risk policies expressly use
operator-supplied research equity: NOT authenticated remote balances.

New external audit-only tool:
scripts/mmt_r42_offline_market_account_evidence_v1.py

No market connections, networking, credentials, plugin execution,
strategy or broker order call, database edit, Telegram or release.

## Strict inputs

Exactly four distinct, absolute, single-link, size-bounded canonical
JSON files, each with independently supplied exact SHA256 hash:
1. POLICY — offline-synthetic-only scope, provider, market, contract,
   symbol, declared region and eligibility list, time period,
   price/volume basis, account alias/currency, freshness bounds.
2. MARKET — two or more closed bars with uninterrupted UTC intervals
   and integer sequences, precise Decimal-string OHLC/volume, explicit
   receive time and max-age check. No gap, replay, wrong source or
   future ticks. This does not authenticate the claimed source.
3. ACCOUNT — provider-labeled synthetic observed-at balance,
   available/margin, all open positions and orders sorted by ID.
4. LEDGER — independent local reference with the same account and
   equity, margin, positions, exact size/side/contract and open orders.

All objects use exact allowlisted fields and integer schema=1,
reject boolean version spoofing, duplicate/noncanonical JSON,
unsorted or repeated exposure IDs, malformed decimals and mismatches.
Received snapshots must fit the independent frozen UTC as-of
timestamp and age windows. Region declaration is NOT authentication.
Only MMT_NONPRODUCTION=1 and no MMT_PRODUCTION key, with explicit
acknowledgement, permits the read-only comparison.

## Verdict is deliberately NOT a production permit

R42_SYNTHETIC_EVIDENCE_MATCH_RELEASE_DENIED means only that the
submitted exact SHA256-pinned synthetic files compare consistently.

Every response returns the false values:
provider_origin_authenticated,
account_owner_authenticated,
region_and_venue_legally_verified,
remote_account_reconciled,
public_signals_authorized,
paper_orders_authorized,
live_orders_authorized,
files_written.

A digest does not authenticate a publisher, provider, jurisdiction
or ownership. The same attacker could fabricate the four files and
hashes. Verification of real API provenance, legal venue eligibility,
account ownership, complete remote exposure and order state remains
independent and PENDING. No actual account or broker was contacted.

## Actual test evidence versus not-yet-tested GitHub suite

Using the assistant's ephemeral Python 3.13.5 environment, pytest
passed **45 / 45** standalone synthetic scenarios in **0.11s**.
Command: pytest -q -c /dev/null -p no:cacheprovider --noconftest.
The checked tool source is BYTE-IDENTICAL to the actual GitHub R42
module verified by Git blob hash:
SHA1 Git blob: 1585edca728f8212ebb79f2da48768b06be14c38
SHA256: 046a34ea4c4959b6ca991e350719120ca885865a78486e48a58bf3a2498b57d6
Size: 14355 bytes.

The GitHub test suite implements 45 equivalent cases but the exact
GitHub test file has NOT been executed in this assistant lab.
Full project suite, Ruff, installed nonroot Python3.12 acceptance,
real provider and account evidence remain PENDING. GitHub Actions
were not invoked due to user quota. No tests executed on Termux,
Telmivo server or a production account.

## Release blockers

Stage15: PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE.
Nine P0 and one P1 remain, including P0_AUTHENTIC_MULTI_MARKET_FEEDS
and P0_ACCOUNT_RECONCILIATION. Frozen Brooks R27 remains deferred,
R37–R41 acceptance gates remain open; owner-only NYFR stays private.
Never merge Draft PR or silently route any real trade or Telegram
notification based on this synthetic comparison.
