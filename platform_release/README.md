# NASERI MARKETS 0.4.0rc1 — isolated public platform preview

This distribution packages the public `naseri_markets` source only.
It exposes typed market contracts, quote-quality gates, explicit in-process
engine registry/runner, paper/forward-observation stores, and optional generic
Telegram transport library code; nothing runs automatically.

The CLI is **offline-only**: `naseri-markets --check` or
`naseri-markets --engine-plan example.json`. It has no activation,
server, channel token, DB migration, order execution or private strategy
download capability.

The historical v0.3.2 `crypto-price-action` release has a distinct
Python package, Dockerfile, Compose project and PostgreSQL volume.
No migration between the two is performed by this candidate.
