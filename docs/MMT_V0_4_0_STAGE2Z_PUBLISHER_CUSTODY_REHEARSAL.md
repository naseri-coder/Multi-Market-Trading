# MMT v0.4.0 — Stage 2Z real-source signer rehearsal (publisher approval pending)

**Scope:** `release/0.4.0-candidate` / PR #352. **No official release authorization.**

## Threat boundary

The existing `scripts/mmt_v040_signed_artifact_preflight_v1.py` and
`scripts/mmt_v040_rc_overlay_signed_custody_v1.py` require a canonical,
externally pinned signed manifest, Ed25519 SPKI fingerprint, trust policy,
signed wheel/RECORD custody, exact source commit, 226 Git source bodies and
an approved one-field RC-to-stable staging transformation.

A successful Ed25519 test with an ephemeral signing key is **cryptographic
interoperability evidence only**. It is NOT proof that a publisher is approved,
that the key is under the release operator's control, or that a signed official
artifact exists. The test key's private bytes are never written to disk or
uploaded. No GitHub Actions repository secret contains a production signing key.

## Real nonproduction GitHub runner rehearsal

`.github/workflows/stage2z-publisher-custody.yml` runs on a fresh GitHub
Ubuntu 24.04 runner using Python 3.12 and pinned build/crypto tooling.

`scripts/ci_stage2z_publisher_custody.py`:

1. Requires `MMT_NONPRODUCTION=1`, `APP_ENV=test` and *absence* of
   `MMT_PRODUCTION`. Rejects a dirty or unexpected Git commit.
2. Checks all **226 real public module bodies** against independent historical
   Git tree `511e9346d88280f3be7c80367f8822a8eaa24dd7` and snapshot SHA-256
   `c2554a8a1c3a46d1675e8e44429c017f6981758df012d5b5feecab353bcf9b9c`.
3. Creates two private disposable, outside-repository source overlays, each
   restricted to the exact `0.4.0rc1` -> `0.4.0` metadata transformation;
   expected SHA-256 `11d87431c863a20514541d8c2aef70e47555d0ca2e2dbd8d1ded11c994ac01d7`.
4. Builds two independent **real-source** wheels (not synthetic source fixtures)
   from pinned reproducible build tools and source-date epoch. Requires byte
   identity and the precise stable Wheel filename.
5. Constructs a **test-only canonical** Ed25519 manifest, detached signature,
   public key and trust policy with a fresh in-memory test signing key.
   Runs the existing stable-artifact signature/RECORD verifier AND the complete
   RC Git source-to-wheel custody auditor over the built real-source Wheel.
6. Replaces the signature with a forgery and verifies rejection; marks the
   ephemeral signer revoked in a freshly pinned test policy and verifies
   rejection. No test failure is waived.
7. Checks that tracked Git source was never modified and deletes ephemeral
   test wheel, policy, public key and signature files on completion.

### Status distinctions

- `STAGE2Z_REAL_SOURCE_TEST_SIGNER_REHEARSAL_PASS_RELEASE_BLOCKED` means a
  real-source Wheel passed a synthetic-key verification *rehearsal only*.
- `independent_approved_publisher_verified=false` is mandatory even if the
  GitHub job becomes green.
- No CI key or self-published policy file is an independently approved trust
  root. Do not replace external pins with values calculated from the untrusted
  artifact directory when performing the eventual real release verification.

## Outstanding *actual publisher* acceptance (not automated away)

The trusted publisher must independently provide:

- Approval of the signer identity/ownership and an externally authenticated
  Ed25519 public-key SPKI SHA-256 fingerprint.
- Signed, independently approved revocation/active-signer trust-policy
  revision and its SHA-256 (with an out-of-band provenance/custody record).
- Exact stable Wheel bytes, canonical manifest and offline detached signature,
  **signed outside shared CI** by the approved private key.
- Independently approved source commit/overlay pins, SHA-256 of manifest and
  wheel, reproducible build and GitHub-runner evidence on the final exact SHA.
- Independent operator/protected-branch review. The source still declares
  `0.4.0rc1`; all stable staging is disposable, not a tag or merge.

Until these external credentials and approvals exist:
**`PUBLISHER_IDENTITY_NOT_ATTESTED__OFFICIAL_RELEASE_BLOCKED`**.
No tag, protected `main` merge, production migration, Telmivo deployment,
Telegram send or LIVE trade is authorized.
