# Stage 28 — Offline publisher identity, key lifecycle and signed ZIP quarantine

**NONPRODUCTION / GitHub-only code. There is no public uploader, login, active plugin marketplace, source loader, trading gateway, Telegram send or production migration.**

Stage28 adds an **owner-reviewed, data-only publisher registry** to the already existing Stage22–27 contracts. Publisher trust remains an explicit offline operator decision; signatures prove possession of an Ed25519 private key, **not** a legal identity, trademark ownership or independent vetting. A future authenticated developer portal must be separately designed and authorized.

## Components and contracts

`naseri_markets.publisher_package_registry_stage28_v1.PublisherPackageRegistry` takes an existing trusted Stage22 ledger and a distinct owner-only, 0700 quarantine directory. On initialization it adds a few new **nonproduction Stage22 SQLite tables**: `secure28_publishers`, `secure28_keys`, `secure28_submissions`, and append-only `secure28_audit`. At most 64 publisher identities can be enrolled locally. No developer personal data, password, source Python module import, private signing keys, cloud OAuth, bot credentials or executable permissions are stored.

**Enrollment:** an authenticated offline operator supplies a trusted tenant ID, reviewed publisher ID, new Ed25519 *public* key and key ID. The publisher signs a short-lived (at most 300-second difference), operator-provided nonce claim using `MMT-STAGE28-PUBLISHER-KEY-ENROLL-V1\0`. This proves possession of that key, not that the uploader is legally the publisher. An explicit nonproduction operator acknowledgment is mandatory. Key starts `ACTIVE`, publisher revision 1; original key IDs cannot be overwritten.

**Rotation:** a new fresh key ID is introduced only when the existing ACTIVE private key **and** the new private key sign the same nonce/issuer/revision claim with `MMT-STAGE28-PUBLISHER-KEY-ROTATE-V1\0`. Stage22 `BEGIN IMMEDIATE` protects CAS revision, marks the old key `RETIRED`, registers the new key `ACTIVE` and logs an audit event as one transaction. Stage23's previous single-key witnesses are *not* silently re-anchored: newly signed candidates require a separately operator-approved Stage23 trust witness for the new key, plus new immutable binding identities.

**Revocation:** explicit owner-approved `revoke(...expected_revision)` marks a key `REVOKED`. Revoking the ACTIVE key permanently BLOCKS that publisher's ability to submit. This version has no silent recovery or key reactivation: a lost-key incident requires separate reviewed re-onboarding policy, not a bypass via a new web account. Retired keys cannot be used to submit new packages. Revocation does not magically delete previous Stage27 registrations; those are already non-executable.

**Auditing:** ordered, append-only SQLite entries `ENROLLED`, `ROTATED`, `REVOKED`, `SUBMITTED`, plus exact locally hashed evidence. Database file ownership remains a host assumption: an actor with OS/SQLite owner privileges could tamper with the ledger or drop triggers; local SHA256 is not an independent immutable external audit.

## Bounded package envelope — no extraction

Stage28 deliberately accepts only a small, **ZIP_STORED** archive with two exact regular-file members:

```text
source.py            <= 65,536 bytes, never imported or executed
descriptor.json      <= 4,096 bytes, exact canonical ASCII JSON
```

The **whole ZIP is bounded to 90,000 bytes** and stored in a separate owner-private quarantine directory under SHA256 filename with O_EXCL+O_NOFOLLOW, 0600 permissions and fsync. It may leave an **unusable orphan** if a crash interrupts the later SQLite commit; it never gives that orphan execution permission. Quarantine file count is capped, and no archive contents are extracted to disk. Nested paths, duplicate members, comments, encrypted or compressed members, ZIP symlinks, oversized members, invalid JSON and extra descriptor fields are rejected.

A canonical descriptor must declare exactly `schema=1`, tenant ID, publisher ID, signing key ID, binding ID, source/manifest/binding/candidate SHA256 and pinned OCI image. Source bytes are verified using existing Stage23 **separately pinned publisher+operator dual signatures** and the exact existing Core API manifest/binding. Crucially, the Stage23 publisher public key must match the **currently ACTIVE** Stage28 roster key, so a previously valid Stage23 candidate signed by a subsequently retired/revoked key cannot enter Stage28.

**Atomic public classification:** after writing inert quarantine bytes, Stage28 rechecks the ACTIVE key and current Stage23 signed candidate while holding the same Stage22 SQLite `BEGIN IMMEDIATE` lock; it reuses the Stage27 internal locked-registration helper to insert the DISABLED binding and the permanent `secure27_public_intake` execution-denial row. The `secure28_submissions` receipt and audit event join this *same* Stage22 transaction. If the transaction fails, none of those database rows remain. Stage27/26 existing protections continue blocking all API or raw-SQL attempts to enable/execute a registered public binding.

An imported `source.py` **is never run**. Stage28 is not a malware scanner and cannot declare a Python file harmless. Operator-facing status includes safe digests, exact binding ID and blocked capabilities; it never displays raw source or secrets.

## Simple trusted-host integration sketch (not a public endpoint)

```python
# objects have been reviewed, keys independently assigned to publisher,
# directories created with 0700 permissions, Stage23 signs an exact source.
registry = PublisherPackageRegistry(stage22_gate, owner_private_quarantine, operator_ack=True)
registry.enroll(tenant_id=tenant, publisher=publisher_id, key_id=key_id,
                public_key=publisher_ed25519_pub, proof_signature=short_lived_proof,
                nonce=operator_nonce, issued_at=now, now=now, operator_ack=True)
receipt = registry.submit(tenant_id=tenant, publisher=publisher_id,
                          key_id=key_id, stage23=stage23_signed_witness,
                          package=zip_bytes, signed_candidate=candidate,
                          manifest=manifest, binding=binding,
                          expected_image=pinned_oci_image, now=now,
                          operator_ack=True)
assert receipt.public_install_authorized is False
```

No HTTP service, JWT, email or Telegram identities were created. The caller MUST authenticate the actual developer/tenant session and validate external publisher authority before invoking these owner-only APIs. Stage27's earlier nonproduction direct signed intake and Stage22's legacy LOCAL_RESEARCH path remain available for existing regression compatibility; **this stage is not a universal barrier against a privileged integrator deliberately routing untrusted files into those APIs**. A later authenticated public entrypoint must mandate Stage28 across all eligible public upload routes, with independent supply-chain approval.

## Validation and remaining blockers

Automated CI uses real ephemeral Ed25519 test keys and only fake/in-memory archives. Positive and adversarial tests cover key possession, stale/replayed rotation, two-key signatures, revoked/retired keys, source/descriptor mismatch, zip traversal, symlinks, duplication, ZIP bombs/oversize, corrupted quarantine, direct Stage22 state changes, Stage27 atomic rollback and legacy Stage22–27 compatibility. Installed-wheel tests run outside the repo source tree. No external network, live host or third-party untrusted program is executed.

**Still NOT READY:** independent actual Docker/gVisor adversarial host acceptance, developer identity onboarding with verified account/session authentication, operator-controlled publisher key escrow/recovery policy, independent key revocation dissemination, per-tenant uploaded-content scanning, trusted installer review, public publication or real exchange actions. The result state is always `QUARANTINED_PUBLIC_SOURCE_NOT_EXECUTABLE`.

**No production DB, live Telegram, broker, server, GitHub secret, or owner-only NY First-Reversal mutation.**
