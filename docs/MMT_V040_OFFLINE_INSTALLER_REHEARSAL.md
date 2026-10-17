# v0.4.0 must include a usable installation file — real full platform, not source-only

**Owner's release requirement (2026-10-18):** A v0.4.0 official announcement **must ship an installation artifact**, not source-only. Preserve all original nine platform CLI entrypoints and existing LIVE source untouched. Post-release feature work remains on `developer`. Apache-2.0 currently unchanged.

**Candidate installer target:** Linux Ubuntu 24.04 with Python 3.12; a non-root, local, entirely **offline** installer bundle: `install.sh`, `multi_market_trading-0.4.0-py3-none-any.whl`, `SHA256SUMS`, `NOT_A_RELEASE.txt` and `REHEARSAL_ONLY.json`.

**Important:** The bundled installer/sha256 file is merely a **technical installer rehearsal**, *not* an authenticated public release. It does not supply a trusted publisher/second-party release signature. Running this installer does not start a bot, access exchanges, send Telegram messages, place real orders or turn on LIVE functionality. Signing/publication must be separately authorized before any official distribution. No production installer should include the `NOT_A_RELEASE.txt` marker; the final signed/published bundle requires its own approval and validation, not an automatic rename.

### Nonproduction execution proof

A workflow on `ci/v040-offline-installer-rehearsal-20261018` fetches the **exact unmodified candidate HEAD** `7bbb3541fb6d63f960bee9f197fe026ed6d04608` into its own clean Git checkout and requires its frozen 226-module source tree SHA `511e9346d88280f3be7c80367f8822a8eaa24dd7` and lock `c2554a8a1c3a46d1675e8e44429c017f6981758df012d5b5feecab353bcf9b9c`. Existing audited stable staging copies only those original Git bodies and makes solely the fixed `0.4.0rc1 → 0.4.0` metadata overlay; expected staged metadata SHA256 `11d87431c863a20514541d8c2eaf70e47555d0ca2e2dbd8d1ded11c994ac01d7`.

Two disposable `pip wheel` builds from the 226 verified actual modules must be byte-identical. Audit all actual ZIP RECORD file SHA256/size fields, 226 source module bytes and the nine console scripts. The installer must check a single exact SHA256 manifest; reject tampered Wheels, malformed manifests, root, defined production flag (including `MMT_PRODUCTION=0`), existing prefix, mismatched Python version and unsafe target. It creates a fresh Python3.12 venv, locally installs `--no-index --no-deps`, verifies nine console script metadata, and safely runs only `naseri-markets --check` and `naseri-paper-demo --help`. Execute the whole installer E2E under a real Linux network namespace without network access. If namespace support is unavailable, fail-closed, not a false PASS.

**Not yet proven:** actual user-facing signal/telegram delivery, live market feeds (Binance/Bybit public tests returned 451/403), real publisher/operator fingerprints, signed public release manifest, OS/Termux compatibility beyond the tested Linux/Python version, or any LIVE trading ability. Root `crypto-price-action==0.3.2` stays separate and unchanged.

**No official `v0.4.0` GitHub Release/tag until** a genuine signed artifact is approved, final exact SHA and main merge accepted and independent review completed. This experiment does not alter PR #352, protected `main` or `developer`.
