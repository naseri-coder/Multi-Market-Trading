# Multi Market Trading — A24 Publisher Trust & Installation Admission

**STATUS: NON-PRODUCTION / SIGNED METADATA ADMISSION ONLY / NO PLUGIN INSTALLATION**

## Owner boundary: NY First-Reversal

NY First-Reversal remains **OWNER_ONLY** and is never available through the
public product installer, registry, sandbox, or commercial-candidate channel,
including encrypted, compiled, obfuscated or otherwise repackaged formats.
Potential owner-only use or later commercial licensing requires its own private
architecture, explicit approval and separate distribution controls.

## What A24 really implements

A24 authenticates a proposed **PUBLIC generic Custom descriptor** and an
operator's specific installation admission, not executable plugin contents.

`a24_publisher_admission.py` defines a bounded canonical JSON envelope with
exact fields:
- `claim`: `schema_version=1`,
  `kind=public_custom_paper_metadata`, A21 engine id/version/publisher,
  pre-pinned publisher key ID, exact independently approved A21 descriptor
  SHA256, target `installation_id`, monotonic `sequence`, issue/expiry
  UTC epoch seconds, `permissions=["paper_analysis"]`,
  `execution_kind=fixed_a23_data_relay_only`,
  `artifact_policy=no_executable_or_ciphertext` and
  `runtime_mode=ephemeral_ci_paper`.
- `publisher_signature_b64`: real Ed25519 over **domain-separated**
  canonical claim bytes.
- `operator_signature_b64`: independently pinned, DIFFERENT Ed25519
  operator key signs another domain containing the exact claim and the
  publisher signature. This avoids assuming that publisher approval
  itself authorizes use in a specific installation.

Unsigned metadata, identity/key substitutions, forged signatures,
duplicate JSON fields, non-canonical encodings, requests for arbitrary
execution, private archives, encrypted bundles, live permissions,
unrecognized schema/fields and timing errors are rejected. No private
keys are held in this public repository or runtime.

### Independent publisher custody and local replay floor

`PublisherAdmissionAuthority` accepts the operator's pre-approved raw
Ed25519 public key with a separately approved SHA256 and independently
registers each publisher's key and key ID. Trust keys do not arrive from
the proposed admission envelope itself. Keys are immutable for this stage,
and revoked publishers are fail-closed (rotation requires a future
separately controlled migration).

The authority uses a separate 0600 SQLite ledger **under the disposable
OS temporary directory** with full-sync durability. It stores only
publisher public keys, operator public key, accepted admission SHA256,
installation+engine binding, monotonic sequence/revision and revocation.
A previous envelope cannot be re-admitted; after supersession it cannot
be used as a current proof. A publisher/installation can be revoked by
the local authorized caller. All current() checks refresh signature,
time, publisher revocation, and the current local ledger proof.

The local SQLite floor is NOT independently tamper-resistant from an
administrator or compromised host, NOT off-host anti-rollback evidence,
and NOT an online/commercial license authority. All keys and signatures
in the tests are generated in disposable CI only.

### Integration with A23 fixed scoped worker and A22 PAPER bridge

`AdmittedFixedCustomSession` is the new **opt-in** route:
1. A21 `public_custom/generic_custom` descriptor is pinned and registered;
2. independent trusted publisher + installation operator create a matching
   double-signed PAPER-only admission;
3. `authority.admit` commits metadata admission with monotonic floor;
4. the wrapper verifies `authority.current` before launching the **same
   static A23 relay**, before heartbeat, and before relaying a PAPER envelope;
5. on invalid, expired or revoked proof, it stops the owned fixed relay;
6. after asynchronous relay, it checks the admission again before passing
   the already-computed PAPER bytes to A22.

It does **not** provision or install an executable artifact. The
existing A23 stand-alone fixture remains available for previous-stage
regressions; A24 does not pretend to globally enforce authority over
that previous demo API. Nor does it promise an atomic revocation check
inside the A22 journal's SQL transaction: a revocation that occurs
after A24's final check but during downstream A22 execution could be
observed late. Production admission would need a stronger atomic
fencing/lease boundary (separate future work).

### No public binary or commerce

A24's returned `AdmissionReceipt` deliberately says
`SIGNED_METADATA_ADMITTED_NO_INSTALL` with `executable_installed=False`,
`private_engine_loaded=False`, `commercial_license_issued=False`
and `live_trading_permitted=False`. A signer can authorize only
**public PAPER metadata**, not plugin code execution, live orders,
publication of the owner engine, proprietary package downloads, or
an installation service.

## CI

A24 dedicated workflow validates real Ed25519 signature composition,
independent trust anchors, key/cert tampering, canonical wire format,
identity and installation binding, publisher/installation revocation,
expiration, monotonic sequence and replay/rollback protection, owner/
commercial/NYFR denial and real A23 Linux fixed relay + A22 paper
journal under disposable GitHub Actions. It reruns A7/A8 and A12–A23
affected tests and checks public-only build context, source freeze,
static imports and documentation. Full PostgreSQL, publication safety
and other repository CI must all succeed before merging.

**Verdict on CI PASS:** A24_SIGNED_PUBLIC_CUSTOM_METADATA_ADMISSION_VERIFIED.
No production, binary installation, commercialization or live trading.
