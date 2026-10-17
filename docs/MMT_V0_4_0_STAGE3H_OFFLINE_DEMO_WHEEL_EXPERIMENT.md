# Stage 3H — Isolated preview Wheel proof, no network, no release authorization

**Status: experiment only.** This commit is on the **separate** branch `ci/stage3h-offline-demo-wheel-20261017`, branched at candidate `7bbb3541fb6d63f960bee9f197fe026ed6d04608`. It is **not** intended for automatic cherry-pick into PR #352 or for production installation.

## Rationale

The existing `multi-market-trading==0.4.0rc1` preview package exposes nine console scripts. The Stage3F proposed public claims list only `naseri-brooks-replay` and `naseri-paper-demo`. Merely advertising two commands does not remove the other seven network/development entrypoints or their importable modules. The prior real source public Binance/Bybit tests returned HTTP **451/403**, and may not be represented as successful live-provider integration.

## Experiment

- Build a **new distinct**, **non-published** `multi-market-trading-offline-demo==0.4.0rc1` Wheel in a 0700 disposable directory from *nineteen allowlisted original* `naseri_markets` Python files (18 static dependency-closure modules plus `public_demo_custom_worker.py` bundled toy).
- Compare the candidate source commit's entire `naseri_markets` Git subtree with the experimental branch — zero product code changes allowed. Exactly the three CI/report experiment files may differ.
- Fail closed on any import of direct HTTP/socket/Telegram libraries or non-allowlisted local Python modules in the staged 19 sources. This **does not claim formal reachability proof against every possible runtime dynamic import**.
- Build two independent deterministic Wheels with pinned setuptools/wheel and `SOURCE_DATE_EPOCH`, compare identical bytes, inspect *actual ZIP contents*, REQUIRE exactly 19 Python files and two exact console scripts.
- Install the real built Wheel in a new isolated Python 3.12 venv, verify package distribution and exact entrypoint names, reject presence of seven other console scripts and inspect that Binance/Kraken network-feed, admin and service Python modules cannot be imported.
- Require a **Linux network namespace with no external network adapters** for exercising the installed offline Brooks help command and a full bundled toy PAPER journey **init → enable → replay → inspect** with a new scratch journal. The subprocess worker is executed inside the same net namespace. If GitHub runner does not permit isolation, **FAIL BLOCKED**, never fall back to internet-connected execution or claim successful isolation.
- Assert that the real PAPER receipt says no broker orders, no Telegram, no release authority; no official signing keys, accounts, production datasets, provider calls or real trades.
- Delete disposable Wheel, installation and PAPER journal at process exit. No artifact upload or package publication.
- Any experiment run PASS proves only the **experimental demo-only Wheel** scope, not the original nine-entrypoint Wheel, which remains unreleased. Any generated checksum is strictly **test-only**, not a publisher-signed stable artifact.

## Next human decision

Even if this experiment succeeds, the owner must explicitly approve whether to publish a distinct **demo-only** distribution or retain the nine-entrypoint **development-only** platform package, reconcile canonical signed RC→stable overlay and source-custody controls, and obtain independent authentic publisher/reviewer Ed25519 identities, protected branch approval, stable exact-SHA tests and human scope exclusion approval.

**No main merge, no `v0.4.0` tag, no Telmivo/Production, no Telegram send or LIVE order.** Issue #354 remains open; PR #352 remains Draft.
