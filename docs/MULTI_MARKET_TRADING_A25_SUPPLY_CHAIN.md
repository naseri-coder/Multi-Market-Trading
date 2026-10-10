# Multi Market Trading — A25 Custom Package Admission & Supply-Chain Security

**A25_NONPRODUCTION_INERT_BUNDLE_ONLY. No real plugin installation or execution.**

## Immutable owner decision: NY First-Reversal

**NY First-Reversal is exclusively OWNER_ONLY.** Nothing from the private
core can be publicly installed, listed for download, redistributed or bundled,
even when encrypted, compiled, obfuscated or subject to a license check.
A25 accepts only **PUBLIC generic Custom** synthetic data fixtures; private,
owner-only or commercial-candidate descriptors are rejected.

## Verified supply chain, no executable artifact

`naseri_markets/a25_bundle_admission.py` implements an independent
**pre-install admission gate**. Its accepted ZIP has exactly two regular,
uncompressed, nonexecutable UTF-8 canonical JSON members:

- `manifest.json` — contract engine ID/version/publisher/ABI, operator-pinned
  descriptor SHA256, exact payload SHA256, fixed inert policy and fixture mode
- `payload.json` — fixed `synthetic_no_signal_data` object with the matching
  engine ID/version and `behavior=no_signal`

ZIP size ≤ 16 KiB, each entry ≤ 4 KiB. Non-ZIP binaries, encrypted archives,
unexpected entries, paths, directories, symlinks, executable permission bits,
ZIP_DEFLATED/compressed entries, duplicate members, unbounded entries, wrong
ABI, wrong versions, extra JSON keys, unknown capabilities, source/ciphertext,
arbitrary entrypoint, forged hashes and ambiguous ZIP prefix/trailer/central
directory all fail closed. **No code is extracted or executed from the ZIP**.

A25 does not treat matching SHA256 as identity proof. Each artifact is
independently double-signed, with **different A25 Ed25519 domains**:

1. Pre-registered, separately pinned **publisher** signature binds immutable
   A21 identity/version, A24 installation and publisher key ID, exact A24
   envelope SHA256, ZIP SHA256, payload SHA256, package version, issue/expiry,
   monotonic bundle sequence and inert-only capabilities.
2. Independently pinned **installation operator** countersigns that exact
   publisher-signed statement. Keys are verified using the existing A24
   custody; no private signer keys are created or stored in public runtime.

Before trust acceptance, A25 validates the **currently admitted A24 envelope**
including expiry, issuer trust and revocation, then the A25 signatures, archive
bytes and matching contract. Artifact sequence and digest are committed
atomically to an independent 0600 **local** disposable SQLite floor.
Old/superseded, mismatched or revoked release proofs fail closed.
The floor is local: **not off-host anti-rollback protection**.

`BundleAdmissionReceipt.state` is
`SIGNED_INERT_BUNDLE_ADMITTED_NO_INSTALL`: this grants neither permission to
install a third-party runtime nor to run real strategy algorithms, access
secrets, write orders, or license proprietary intellectual property.

## Lifecycle integration

The **optional** `A25GuardedFixedFixture` checks current A25+A24 admission
before A23 fixed subprocess launch and heartbeat, and before/after its
A24/A22 PAPER data-dispatch wrapper. An expired or revoked package stops the
owned non-production fixture. This is a *fixed bytes-only relay*, not a
generic engine executable installer.

**Known atomicity limitation:** A24/A25 checks are not part of the downstream
A22 journal SQL transaction. A revocation occurring after the last check but
during A22 commit may allow a PAPER record before the next detection.
A25 also checks after its awaited downstream call, but such a late check
cannot undo a prior commit. This gap must be closed in a separate stage
before any production-grade authorization claims. The A23 and A24 legacy
fixture-only APIs remain accessible for their existing tests: A25 does not
retroactively enforce this policy on every possible entrypoint.

## Checks and evidence

`tests/unit/test_a25_bundle_admission.py` probes signed release identity,
wrong publisher/operator, bounded ZIP parsing, malicious archive traversal and
symlink/executable payloads, wrong ABI/manifest/engine, canonical JSON,
independently pinned SHA256, expiry, downgrade/replay across independent
SQLite connections, revoked A24 authority, revoked A25 release and actual A23
Linux systemd cgroup + default-deny seccomp + A22 PAPER journal.
The dedicated A25 GitHub workflow reruns A7/A8 and A12–A24 regressions,
historical source hash freeze, public-only release preflight and absence of
any NYFR, binary/ciphertext artifact or dynamic strategy loader.

**This is supply-chain research using disposable synthetic content, not
a production-capable plugin marketplace, third-party code sandbox, publisher
PKI, commercial license server or proprietary strategy distribution route.**
