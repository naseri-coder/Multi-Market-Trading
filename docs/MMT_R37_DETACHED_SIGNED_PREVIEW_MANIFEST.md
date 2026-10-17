# R37 — Detached Ed25519 preview manifest verifier (Draft, NO release)

This phase begins work on **publisher trust** for the isolated public-only
`multi-market-trading==0.4.0rc1` Wheel; it does not authorize installing,
signalling, activating Telegram/brokers or LIVE trading.

## Bounded components

- `scripts/mmt_r37_offline_signed_manifest_verify_v1.py` is **read-only** and
  requires Python 3.12 plus `MMT_NONPRODUCTION=1`.
- Verifies a strict canonical JSON manifest (UTF-8 ASCII-escaped,
  sorted keys, compact separators, exactly one terminal newline),
  a separately stored **raw 64-byte Ed25519 detached signature**, and
  cryptographic domain separator:
  `b"MMT-R37-OFFLINE-PREVIEW-MANIFEST-V1\n"`.
- Requires a trusted Ed25519 **public** PEM key and its independent
  operator-approved SHA256 fingerprint of DER SubjectPublicKeyInfo
  (`--trusted-public-key-spki-sha256`). This fingerprint is NEVER accepted
  from the manifest itself. A separately reviewed 40-digit Git commit
  (`--expected-source-commit`) is also mandatory.
- After Ed25519 signature validation, checks the exact bytes/size of
  the locally provided Wheel against those asserted by the signed
  manifest. Rejects noncanonical/duplicate JSON, unexpected purpose,
  wrong version, public key, fingerprint, source pin, signature,
  Wheel hash/size, symlinks and out-of-scope production mode.
- The tool only **verifies**, never generates or stores a signing key.
  The 13 synthetic unit tests generate temporary throwaway keypairs
  exclusively in isolated test directories.

**Warning:** Successful R37 verification attests a *specific external
trusted key signed the canonical preview metadata* and those signed
Wheel bytes match the local file. It **does not** establish the real
publisher's identity without independently authenticated custody and
distribution of the key fingerprint. It does not prove the provenance
of the reviewed Git SHA or inspect package code. Retain the R36
Git↔Wheel source and RECORD audit as a separate required check.

## Manifest schema v1 (example field types; not a real signed release)

```json
{"distribution":"multi-market-trading","purpose":"offline-preview-only","schema":1,"source_commit":"1111111111111111111111111111111111111111","source_date_epoch":1704067200,"version":"0.4.0rc1","wheel_filename":"multi_market_trading-0.4.0rc1-py3-none-any.whl","wheel_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","wheel_size":787808}
```

The actual manifest MUST be generated with
`json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`
then a single `b"\n"` appended. The signature is over
`DOMAIN + manifest_bytes`. The fingerprint is SHA256 of the
**DER SPKI** representation of the trusted public key, not of its PEM
text. The signer must use an **independent, protected MMT release key**
outside GitHub, not a Telegram key, existing Telmivo signing key or
private NY First-Reversal resource.

## Verification command (only after an independently established trust anchor)

```sh
MMT_NONPRODUCTION=1 /usr/bin/python3.12 \\
  scripts/mmt_r37_offline_signed_manifest_verify_v1.py \\
  --manifest /path/to/canonical-preview-manifest.json \\
  --signature /path/to/canonical-preview-manifest.sig \\
  --wheel /path/to/multi_market_trading-0.4.0rc1-py3-none-any.whl \\
  --trusted-public-key /path/to/approved-mmt-ed25519-pub.pem \\
  --trusted-public-key-spki-sha256 <INDEPENDENTLY-VERIFIED-SHA256> \\
  --expected-source-commit <INDEPENDENTLY-VERIFIED-GIT-SHA>
```

The verifier is an **external audit tool** and uses the optional
`cryptography` Python package. It is not introduced as a platform
runtime dependency or silently installed into the user's working
PRoot. Pin, acquire and verify cryptography dependencies separately
before any real operator acceptance. No publisher private key,
signature or authenticated public-key fingerprint currently exists
in this Draft. **Real-publisher verification remains pending.**

## Validation status and strict boundaries

- R36 accepted: 221 matching modules, wheel RECORD integrity,
  13 unit tests, pinned separate build tools, two same-host
  fixed-SOURCE_DATE_EPOCH builds byte-identical at SHA256
  `37c18d73978ecc48febc3a56e79b8ac65da6d77bce7b18ea68db44212c2c5ee4`.
- R37 implementation is newly added as a separate Draft branch stacked
  on R36. 13 synthetic tests passed in the assistant's **Python 3.13
  separate lab** with `cryptography`; this is **not** a real operator
  Python 3.12.3 pass and test fixtures temporarily substitute 3.12
  version info to exercise in-scope logic. No real publisher signing
  key or actual release signature used.
- An actual operator Python 3.12 test run, independent key
  authenticity verification, key revocation and protected storage
  procedures, deployment/installer integration, and independent host
  security review remain out of scope.
- Stage15 has **9 P0 + 1 P1** still-open product release blockers;
  R27 frozen Brooks full worker remains deferred. Always return
  `public_release_authorized=false`, `live_authorized=false`,
  `install_authorized=false` on successful R37 verification.
- Do not merge Drafts, connect PAPER, activate broker or Telegram,
  modify the legacy crypto-price-action runtime or expose NYFR.

## 2026-10-16 security hardening and assistant-local regression report

Follow-up review identified a production-environment bypass:
`MMT_PRODUCTION=0`, `true`, `YES`, or even an empty string
could coexist with `MMT_NONPRODUCTION=1` and pass the initial
prototype's narrow `MMT_PRODUCTION == "1"` test.

**Remediated:** R37 now refuses **any presence** of the
`MMT_PRODUCTION` environment variable, not merely the value `1`.
This is deliberately stricter than historical preview tools and
cannot enable any release privilege.

Extended the dedicated synthetic unit suite from **13 to 23 cases**:
the original signature, trusted-key, signed source pin, Wheel hash,
canonical JSON, duplicate-key, symlink and no-release checks plus
four explicit production-flag values, missing nonproduction opt-in,
signed boolean epoch, Wheel symlink, multi-hardlink manifest, actual
CLI valid-signature deny-only output and actual CLI forged-signature
refusal. Test-only Ed25519 key material is ephemeral, held only in
the assistant's disposable sandbox, and **never copied to GitHub**.

The assistant's separate local lab ran **23/23 PASS** with
Python **3.13.5**, `pytest 9.0.2` and
`cryptography 46.0.4`, including an actual CLI success/failure
cycle and no public/LIVE grant. This is **synthetic functional
evidence only**: the tests monkeypatch `sys.version_info` to
exercise the Python 3.12 gate. Python 3.12-specific execution and
Ruff have **not** been run in this lab; no actual release publisher
key, approved SPKI fingerprint, real signed public Wheel or
key-custody review was available. No connected host/Telegram/broker,
Termux operator action or release merge occurred.

Disposition:
`R37_DRAFT_SYNTHETIC_VERIFIER_TESTS_23_PASS`
with `R37_REAL_PUBLISHER_SIGNATURE_PENDING` and
`PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE`.
Before counting R37 as fully operationally accepted, acquire
independent custody/rotation/revocation authorization for a
dedicated publisher key, verify actual signed public Wheel on an
approved Python 3.12 host and perform separate R36 Git/RECORD checks.
**Do not** reuse a Telmivo signing key, commit a private signing
key, disable the absence-of-trust-pin checks, or merge the Draft.
