# NASERI MARKETS — GitHub-only migration plan

Status: **A1 FOUNDATION / NO SERVER REQUIRED**

The user reports that the former server installation was removed. This removes
a live-service cutover requirement. It does NOT remove requirements for clean CI,
publication safety, data privacy or preserving a recoverable release history.

## Confirmed GitHub baseline (inspection 2026-10-09)

- Repository: naseri-coder/crypto-price-action (PUBLIC)
- Main commit: 86407bc51e019951126403074344f7551274bc3c
- Current packaged runtime: production_source/app/
- Existing Brooks runtime, FM runtime with isolated registry, market_data, risk,
  signal_strategies and Telegram integrations
- Frozen v0.3.2 SHA256SUMS release guard and companion GitHub Actions
- Existing operational names in compose.yaml, scripts, CLI, runtime image and
  several historical docs

## Sequenced migration

A1 (this PR): proposed NASERI MARKETS branding, offline multi-market contracts,
registry, routing policy, documentation, tests; **no live integration**.

A2: separate new platform runtime and instrument registry; broker adapters and
session calendar, timezones/DST and per-provider tick quality; no secret core.

A3: engine lifecycle, separate per-engine/private-channel routing, deterministic
idempotency, durable signal lifecycle and forward P&L observation with gap/unknown.

A4: privately connect NYFR through the public boundary. Verify original source
and strategy decisions outside this PUBLIC repository. No MT5 orders.

A5: migrate existing Brooks/FM integrations in the GitHub codebase with regression
coverage, reconcile frozen source manifest under a new release version.

A6: coordinated rename of release/Compose image name, CLI, environment template,
manager/install scripts, documentation, workflow tags and repository slug. Old
tagged releases remain immutable. Run full CI before merge. Repo slug rename
requires a GitHub administration action and is not performed in A1.

Later: execution-capable MT5 client, server-side license authority,
revocation/anti-replay and security audits **only after forward validation**.

## Release integrity caveat

Do not edit production_source/SHA256SUMS or historic immutable release evidence
to disguise drift. The public snapshot's original source hash contract is not
the starting point of a new release until specifically re-baselined and audited.

## Explicit non-goals

No production server changes, private source upload, Telegram messaging,
live market connections, simulated claims of profitability, or MetaTrader orders.
