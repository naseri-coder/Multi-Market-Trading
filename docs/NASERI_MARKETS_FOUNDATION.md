# NASERI MARKETS — Multi-Market Platform Foundation (A1)

Status: **DEVELOPMENT FOUNDATION ONLY — NOT DEPLOYED, NOT TRADING**.

## Goal

Evolve the former **Crypto Price Action** public snapshot into a market-agnostic,
multi-engine signal platform. Brooks remains one crypto engine; NY First-Reversal
(NYFR) is a distinct index-market research engine, not a Brooks module.
Future engines may support FX, metals, and additional instruments.

## Public versus private boundary

This repository is PUBLIC under its existing licence. Any pushed strategy
implementation becomes accessible to the public. Only market identities,
engine metadata, signal-envelope contracts, fail-closed delivery policy, tests,
and documentation belong in this repository.

**Never commit NYFR private rules, thresholds, proprietary features, credentials,
channel identifiers, live tick records, commercial license keys or trade secrets.**

Private engine implementation: separate private repository/secret-managed runtime.
A private engine will eventually depend on a versioned contract package and a
trusted deployment adapter; the public repository must not import private code.

## Planned architecture

1. Market data adapters: Binance/crypto, authenticated FX/index/metal feeds;
   normalize exchange time, broker-local time, IANA session timezone, Bid/Ask,
   tick timestamps and instrument contract specifications.
2. Engine contracts: immutable instrument identity (market + provider + symbol);
   engine identity/version; observed signal intent with validated risk geometry.
3. Registry: explicit engine versions and supported markets; no implicit imports.
4. Lifecycle isolation: dedicated engine namespace and persistent signal
   deduplication key. Broker feeds, strategies, risk, analytics and publication
   remain independently versioned.
5. Independent Telegram routes: engine/market-scoped, default disabled; verify
   private channel through Telegram API before publishing any real signal.
6. Evidence stores: never combine historical, simulated, forward-observed or
   broker-filled results. Forward results require observed Bid/Ask and gap tracking.
7. Security: least-privilege separation for private engines and channel bots.
   Later MT5 execution clients and licenses belong to a different approved stage.

## What A1 actually implements

The root-level 'naseri_markets/' package is an OFFLINE prototype of contracts,
metadata registry and delivery decisions. It is intentionally not included in
the production package, Docker image, source manifest, runtime, or Telegram bot.
There is NO MT5 connection, NYFR trading logic, live data listener, sending or
automatic order execution.

This isolation preserves the frozen v0.3.2 source manifest and existing public
release tests. A subsequent stage can replace legacy module-specific adapters
with versioned, tested bridges after a source provenance and dependency audit.

## Safety invariants

- Deny unknown engine/version/market.
- Deny any route unless explicitly enabled and independently verified.
- Historical or paper-mode intents never masquerade as forward observations.
- Never treat a signal intent as a filled trade.
- Never infer broker execution or real-time profitability from an offline test.
- No public Git history may contain proprietary strategy implementation.
