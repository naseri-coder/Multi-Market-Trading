# Multi-Market-Trading v0.4.0 — Offline Platform Release

Official open-source source-and-binary release: 226-module `multi-market-trading==0.4.0` Wheel, nine original CLI entrypoints, locally verified `install.sh` for Ubuntu 24.04 with Python 3.12, `SHA256SUMS`, `RELEASE_MANIFEST.json` and `ASSET_SHA256SUMS`.

**Supported release scope: OFFLINE/NONPRODUCTION and research/PAPER.** Not a production live trading application. Actual Binance/Bybit market-data connectivity is NOT verified: opted-in public tests failed HTTP **451 / 403**. Real Telegram sends, arbitrary customer plugin security, LIVE brokerage orders and live-market profitability are not certified. Existing LIVE source code is preserved; future improvements occur on `developer`.

Download `install.sh`, `multi_market_trading-0.4.0-py3-none-any.whl`, `SHA256SUMS`, and `RELEASE_MANIFEST.json` to the **same local directory**. On Ubuntu 24.04/Python3.12 as a non-root user:

```bash
MMT_NONPRODUCTION=1 bash install.sh --prefix "$HOME/mmt-v0.4.0"
```

This installer checks the Wheel SHA256, release manifest and exact distribution metadata; installs without network in a new virtual environment. It does not auto-start a bot, contact exchanges, send Telegram or place orders. Explicitly defined `MMT_PRODUCTION` (even 0) and existing installation prefixes are refused.

**Authenticity (online before installing):** GitHub Actions attests Wheel and installer via OIDC/Sigstore signed build provenance. Verify the Wheel with:

```bash
gh attestation verify multi_market_trading-0.4.0-py3-none-any.whl --repo naseri-coder/Multi-Market-Trading
```

`ASSET_SHA256SUMS` validates byte integrity of all assets; ordinary SHA256 alone is not publisher authentication. GitHub OIDC attestation verifies workflow provenance, not an independently supplied human signing key.

The stable Wheel was built from the exact Git-sourced 226 modules at commit `7bbb3541fb6d63f960bee9f197fe026ed6d04608`, integrated into protected main by PR #352. The audited staged Python distribution metadata overlay changes `0.4.0rc1` to `0.4.0`; the historical separate `crypto-price-action==0.3.2` package remains unchanged. Apache-2.0 license retained. Android Termux compatibility is not yet tested.

**Risk notice:** simulated PAPER outcomes do not prove actual profitability or live-execution safety. Use only in a nonproduction research environment.
