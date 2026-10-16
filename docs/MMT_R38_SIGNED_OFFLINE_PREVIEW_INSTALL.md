# R38 — Signed, revoked-key-aware, opt-in offline-preview installer (Draft)

**No public or LIVE release authorization.** R38 is a new stricter entrypoint,
stacked on R37 #330. It does **not** modify the preexisting unsigned
R35 *nonproduction preview* installer, which remains independently callable.
Thus R38 does not make signing mandatory across all possible installation
paths; universal signed-release enforcement needs a separately reviewed
migration decision.

## Verified trust inputs and order

The script is scripts/mmt_r38_signed_offline_preview_install_v1.py.
It requires **Python 3.12**, MMT_NONPRODUCTION=1, and **no**
environment variable named MMT_PRODUCTION, regardless of its value.

The following checks occur before any installation write:

1. **Independently pinned trust-policy SHA256** is mandatory.
   The canonical JSON policy contains exactly schema=1,
   revision (positive integer), active_keys (array of DER-SPKI
   SHA256 fingerprints), revoked_keys (array), and
   min_source_date_epoch. Duplicate, overlapping, malformed or
   oversized key sets are rejected. The signer must be active
   and **not** revoked. A local revocation snapshot is only as
   fresh as its externally approved pinned digest.
2. **Independently pinned canonical manifest SHA256** is required,
   along with separately approved Git commit and DER-SPKI key
   fingerprint. A signed build epoch below the policy minimum
   is rejected as an old manifest. The trust anchor is never
   sourced from the self-signed or self-authored manifest.
3. The actual R37 verifier checks domain-separated detached
   Ed25519 signature and matches the local Wheel SHA256 and size.
4. The actual R35 checker validates the bounded public Wheel ZIP,
   exact metadata, and safe new destination under a 0700 owner-only
   directory outside the checkout.
5. The installed variant adds the existing R35 non-root and explicit
   acknowledgement gate. Only after successful signature checks
   can R35 install via pip --no-index --no-deps and run its inert
   installed naseri-markets --check. R35 recomputes the signed digest.

## Preview-specific result and failure behavior

Read-only check-only does not create an installation directory. A
successful nonproduction install creates a 0600 local
signed-preview-install-evidence.json under the new private R35
destination, preserving the externally pinned policy hash/revision,
manifest hash, source commit and signer key fingerprint. No private
signing key is generated, stored or used.

Wrong signature, inactive/revoked key, wrong independent pin, old
manifest, Production environment or preexisting destination means
**no install write**. Once R35 creates the destination, a subsequent
error leaves that partial private directory for operator inspection;
there is **no automatic cleanup or rollback** of Python package code.
This explicit fail-closed rule prevents the user from mistaking a
partly installed path for a successful signed deployment.

The signed-preview mechanism does not prevent local unsigned use of
the older R35 *preview* CLI. It does not provide a network/firewall
sandbox, actual publisher identity, independently audited key custody,
signed revocation feed, complete rollback of code execution,
autonomous key rotation or authorization of market providers.

## Example policy values (illustrative; NOT a trusted publisher key)

schema: 1
revision: 1
active_keys: ["1111111111111111111111111111111111111111111111111111111111111111"]
revoked_keys: []
min_source_date_epoch: 1704067200

Serialize policy JSON with sorted keys and compact separators,
a trailing newline, and ASCII escaping. Independently verify the
**exact SHA256 of those bytes**, the signer DER-SPKI fingerprint
and the source Git commit before invoking R38.

## Required CLI inputs

manifest, signature, wheel, trusted-public-key,
trusted-public-key-spki-sha256, expected-source-commit,
expected-manifest-sha256, policy, expected-policy-sha256,
destination, and exactly one of check-only or install. Installing
requires ack-offline-preview-install. All CLI inputs must use the
matching long --argument form.

All result paths and release privilege fields remain deny-only:
public_release_authorized=false; live_authorized=false;
broker_orders_enabled=false; telegram_enabled=false.
The install_authorized=false field means there is **no operational
publication entitlement**; explicit nonproduction installation
may occur in the disposable offline lab with acknowledgement.

## Test, acceptance and outstanding blockers

The R38 unit module defines 20 synthetic cases: valid signed
read-only preflight, missing/forged signature, wrong policy and
manifest pins, revoked/inactive signer, replayed signed epoch,
source pin, Wheel tampering, swapped public key, duplicate
trust-policy JSON key, Production flag, existing install target,
root refusal, missing ack, no premature R35 execution, successful
mock-only install report and refusal after an unsafe installer
response.

As of the initial Draft, real operator Python 3.12.3,
actual independent signed publisher release, rootless OS host
security and public rollout remain **PENDING**.
Do not connect Telegram, broker, services or LIVE, and do not
use the operational Telmivo server to test this feature.
Stage15 retains nine P0 and one P1 blocker. R27 Brooks full-core
worker evidence remains deferred; all stacked PRs are unmerged.


## Execution verification caveat and version pin

Static source/PR inspection confirms that the R38 entrypoint delegates
cryptographic trust verification to R37 and Wheel metadata checks to R35
**before calling** R35 installation. The 20 authored tests have **not**
yet been executed against Python 3.12.3 with the optional cryptography
dependency in a clean disposable host; no synthetic pass or exact
Ruff result is claimed. Pending user-device-dependent tests are not
silently treated as passed.

For a genuinely read-only operator check, launch from a clean
nonproduction environment with PYTHONDONTWRITEBYTECODE=1 to avoid
Python import cache writes into the source checkout. The R38
application's check-only business logic itself creates no files,
but a default Python interpreter might otherwise emit __pycache__.
An attacker-owned or writable environment is **not** a security
sandbox, even with both signed pins and pip --no-index.
