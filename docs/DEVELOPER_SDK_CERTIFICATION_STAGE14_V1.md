# Stage 14 — Developer SDK & Core Certification (offline / nonproduction)

## Baseline and scope

This release adds a public, provider-neutral SDK for independent strategy authors against **existing Core API v1 (`ABI 1.0`)** and the offline Stage-4 pinned single-file worker protocol. The strategy declares **setups**, supported market classes and event types; it may define entry/stop/targets and optional strategy stop-management logic. A strategy **must not** embed venue, broker, symbol, user account, balance, leverage, channel destination, execution authority, or live credential. Those are owned by the existing platform binding and risk systems.

Stage-14 SDK packages are offline source artifacts, **not installable packages**. This stage does not modify a running bot, server, PostgreSQL, public plugin registry, or NY First-Reversal. No market order, Telegram message, external market-data fetch or third-party code execution is enabled.

## SDK contract and reproducibility

New source files:

- `naseri_markets/core_developer_sdk_v1.py`: exact-schema manifest parser using existing `CoreManifest`, source-byte validation, conservative AST lint, canonical deterministic ZIP construction, rejection of noncanonical/unsafe ZIP encodings, size cap compatible with Stage 4 (source <= 65536 bytes), and inspection that **never extracts or executes code**.
- `naseri_markets/core_certification_v1.py`: Ed25519 detached signature creation/verification with explicit pinned public-key trust roots, revocation, domain separation and report that always requires external review.
- `examples/sdk/core_template_v1.py`: safe known *NO_SETUP* demonstration speaking Stage-4 JSON protocol. It deliberately makes no claim of edge, PnL or profitability.
- `examples/sdk/manifest_v1.json`: declaration example; generated manifest includes source SHA-256.
- `scripts/mmt_core_sdk_v1.py`: offline pack / inspect CLI (no automatic execution).
- `tests/unit/test_core_developer_sdk_v1.py`: positive/negative and tamper/security contract tests.

Canonical package has exactly two members: `manifest.json` and `plugin.py`, ordered, ZIP_STORED, fixed timestamps and POSIX metadata; its exact bytes are reproducible. Manifest contains **no platform binding settings**. The plugin source digest pins bytes; its package digest pins both manifest and code. Duplicate JSON fields, unsupported ABI, duplicate setups/markets, invalid decimal/market contract, traversal paths, extra members, compressed zip variants, symlinks/metadata deviations, oversized members and malformed sources are rejected. Inspection never imports the candidate source.

### Example from repo root

```bash
python -m scripts.mmt_core_sdk_v1 pack \
  --manifest examples/sdk/manifest_v1.json \
  --source examples/sdk/core_template_v1.py \
  --output /tmp/core-candidate.zip
python -m scripts.mmt_core_sdk_v1 inspect --bundle /tmp/core-candidate.zip
```

Never commit the generated `.zip` to the repository (publication-safety rejects archive artifacts). The CLI refuses overwrite of existing output paths. All content is reviewed before potential use by a separately authorized worker; `pack` is not `install` or `run`.

### Signing (operator-only, not GitHub CI)

`cryptography` is **optional** for signing and validation and must be explicitly installed in a separate reviewed SDK operator environment; it is not added to existing locked production requirements. An externally managed 32-byte Ed25519 secret seed may be used with `sign_package(bundle, key_id=..., private_seed=...)`. Keep private keys outside repository, CI, logs, chat, Telegram and built artifacts. Distribute only a detached JSON signature containing key ID, algorithm, artifact SHA-256 and base64 signature. `verify_signature(bundle, signature, trust_roots={"publisher_key_id": public_key_bytes}, revoked_key_ids=...)` uses exactly the supplied trusted Ed25519 public key; no implicit trust or unknown publishers. Rotated/revoked keys must be fenced by the calling operator.

A valid signature proves *package-byte authenticity relative to a pinned publisher key*, not safe source code, license compliance, benign behavior or profitability.

## Certification: fail-closed stages

1. **STRUCTURAL REVIEW:** strict ABI and source digest; deterministic artifact, no embedded deployment config. Strict static linter rejects common unsafe import/call patterns; AST analysis is only *heuristic defense in depth*, **not a sandbox**.
2. **PUBLISHER SIGNATURE REVIEW:** optional Ed25519 signature over an unambiguous, domain-separated artifact digest; operator maintains key trust/revocation independently. Unsigned packages remain blocked from public distribution.
3. **INDEPENDENT SOURCE & SUPPLY-CHAIN REVIEW — NOT COMPLETED:** human review, license, provenance, reproducible build verification, malicious package scanning, dependency/entrypoint audit and signature key custody.
4. **ISOLATED-HOST ADVERSARIAL TESTS — NOT COMPLETED:** real disposable rootless Docker + gVisor `runsc`, resource/orphan stress, sandbox escape challenge, no secrets/network, crash and restart validation. Prior Stage-4 mocked command tests are not sufficient.
5. **PUBLIC CATALOG / EXECUTION AUTHORIZATION — NOT IMPLEMENTED:** risk/account/market eligibility, per-user permissions, approved plugin registry, signed release and rollout/rollback fencing require separate authorization and development stages. No trust assertion is converted to `enabled=True`.

`evaluate_candidate` always returns `REVIEW_REQUIRED_NONPRODUCTION` with explicit open blockers and all permission booleans **False**. Invalid signatures refuse rather than falling back to unsigned. Full runtime security, business compliance and live trading remain unverified.

## Acceptance tests and limitations

Run: `python -m pytest -q tests/unit/test_core_developer_sdk_v1.py`. Cryptographic key tests use optional `cryptography` if installed. The example protocol fixture may execute only the repository's **known harmless** worker as a subprocess in local tests. The SDK will **never** run third-party package code in host Python. The new certification path cannot be used to bypass Stage-4 host restrictions or Stage-6 Iranian-resident eligibility policy. Past modules are unchanged.

Expected stage verdict, once files are merged and checks pass: `STAGE14_SDK_STATIC_CERTIFICATION_NONPRODUCTION_PASS`. This does **not** imply `CORE_CERTIFIED_SECURE` or `PRODUCT_READY_FOR_LIVE`.
