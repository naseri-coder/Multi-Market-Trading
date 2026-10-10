# Public Brooks signal management — nonproduction

The Brooks Price Action engine is a **public built-in** engine in the
Multi Market Trading Telegram administrator's engine list.

The panel provides separate per-engine switches for **analysis requested**
and **signal publication requested**. A selected private channel, timeframe,
market, OFF/PAPER mode, and audit history are independently managed.

**Crucial runtime distinction:** The legacy Brooks analyzer still resides
in the SHA-frozen `production_source` tree. The new v0.4 runtime does
**not yet mount or execute** that analyzer. An enabled request is **not**
a running analyzer. Similarly, `requested_publication=true` is **not**
a permission to send: `effective_publication=false` always, with reason
`NO_AUTHENTICATED_FORWARD_PUBLISHER`. There is no forward market feed,
verified end-to-end publishing, or live signal emission in this change.

NY First-Reversal is a private owner-only Custom reference; this public
repository contains **no proprietary engine source or executable**.

This stage is a public GitHub feature branch and tests; no server or
running bot is modified. Future implementation of real Brooks PAPER
analysis requires an explicitly reviewed, reproducible analyzer adapter
and causal candle replay contract, without silently changing the legacy
production source. Real channel publishing requires separate authenticated
forward data, idempotency and explicit deployment authorization.
