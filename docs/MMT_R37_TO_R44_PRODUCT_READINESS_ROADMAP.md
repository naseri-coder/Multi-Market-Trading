# Multi-Market-Trading: bounded roadmap R37–R44 (2026-10-16)

**Status: proposed 8 engineering milestones from the current R36 supply-chain
evidence; R37 DRAFT/SYNTHETIC-TESTED; R38 DRAFT IMPLEMENTED/NOT ACCEPTED; R39 DRAFT/NOT ACCEPTED; R40 DRAFT/NOT ACCEPTED; R41 STATIC AUDIT DRAFT/NOT ACCEPTED; R42 SYNTHETIC AUDIT DRAFT/NOT ACCEPTED; R43–R44 NOT STARTED.** This is an planning
structure, not an assurance that eight phases suffice to certify
broker-connected/live operation. Keep all PRs Draft/unmerged until their
acceptance and the separate integration policy is resolved.

## Current verified baseline

- R34 original `multi-market-trading==0.4.0rc1` public-only Wheel
  (offline synthetic preview), R35 hash-pinned deny-only installed
  functional PRoot preview, and R36 source↔Wheel and PEP427 RECORD
  checks, 13 isolated unit tests, reproducible **same-host** fixed
  `SOURCE_DATE_EPOCH` Wheel pair. Not independent signed provenance.
- `naseri_markets/release_readiness_v1.py` `_OPEN_BLOCKERS` currently
  defines **nine P0 and one P1 blockers**. Its
  `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE` verdict is
  deliberately irreversible by software test results alone.
- Frozen R27 full Brooks worker smoke is deferred. Legacy
  `crypto-price-action==0.3.2`/root launcher is separate from the
  v0.4.0rc1 preview. NY First-Reversal is strictly OWNER_ONLY.

## Milestones and exit criteria

| Phase | Bounded work | Concrete exit evidence | Status |
|---|---|---|---|
| **R37** | Define canonical signed preview manifest, independent pinned trust anchor and fail-closed Ed25519 verification; no real private key in repo | External key custody/revocation policy, authenticated key fingerprint and Python 3.12 negative tests; signed *preview* only | **DRAFT IMPLEMENTED: 23 assistant-local synthetic tests PASS; real publisher key and Python 3.12 acceptance PENDING** |
| **R38** | Separate signed-only *preview* wrapper with externally pinned trust policy; no change to unsigned R35 alternate preview path | 20 authored synthetic denial cases; requires actual Python 3.12 test, real publisher trust, nonroot installation evidence and signed-path migration review | **IMPLEMENTED DRAFT #331; TEST EXECUTION/REAL SIGNER PENDING** |
| **R39** | Add dedicated nonroot, one-fixture synthetic PAPER authority journal ahead of existing Stage20 and Stage10 read-only reopen; no general runtime yet | 20 authored test cases include real two-binding synthetic integration, PENDING/QUARANTINED/no-auto-retry, drift and read-only receipt checks; genuine Python3.12 acceptance pending | **DRAFT CODE AUTHORED — NOT ACCEPTED, STAGE15 P0 STILL OPEN** |
| **R40** | Read-only installed R39 synthetic PAPER acceptance inspector, module/source pin and six local SQLite content fingerprints; R27 Brooks explicitly DEFERRED | Authored 24 test functions with negative scenarios. Genuine newly built wheel, nonroot Python3.12 host, interrupted-job proof and Brooks full-core independent evidence all PENDING | **DRAFT CODE AUTHORED; NOT ACCEPTED; BROOKS DEFERRED** |
| **R41** | Read-only SHA-pinned Stage4 OCI source/command hardening audit and independent hostile-host acceptance plan; no Docker execution | 23 authored static denial cases; actual rootless Docker + gVisor, hostile plugin/escape/cleanup and independent reviewer evidence remain PENDING | **DRAFT STATIC AUDIT, HOSTILE-HOST P0 OPEN** |
| **R42** | Strict read-only, four-pin synthetic feed/account-versus-ledger comparison with contract, UTC market freshness and exact position/order consistency | **45/45 assistant-local Python 3.13 synthetic cases passed on byte-exact GitHub module; real feed/account attestation, venue region policy and Python 3.12 operational acceptance PENDING** | **DRAFT IMPLEMENTED — P0_FEEDS/ACCOUNT OPEN** |
| **R43** | Authoritative Telegram receipt/UNKNOWN reconciliation and durable recovery/rollback/incident rehearsal | Private sandbox delivery acknowledgements and backoff, replay-proof outbox; restore, multi-worker soak, migration dry-run | PENDING |
| **R44** | Independent Stage15 go/no-go audit, research P1 unbiased performance evidence, migration and operational release authority | Each of nine P0 + one P1 independently closed with dated reproducible evidence; real external review | PENDING |

## Counting rules

- **8 named phases R37–R44 inclusive**. R37 is drafted, and R38 is drafted but **not accepted**; **2 later named phases R43–R44** remain in this proposed roadmap, plus R37/R38 outstanding trust and acceptance gates.
- This is an **estimate of engineering bundles**, not the exact number
  of approvals, tests, PRs or calendar days required. Failed gates may
  add phases and independent-host validation cannot be performed on
  GitHub alone.
- Passing R44 would only permit a separately scoped *human* release
  decision; it would not silently turn on LIVE trading, publish
  Telegram signals or authorize unsupported providers. LIVE requires
  a separately approved broker, KYC/sanctions, capital-risk,
  monitoring, kill-switch and incident-control program.

## Execution strategy to minimize operator Termux commands

1. Use the connected GitHub connector for source reviews, branch and
   Draft PR creation, test fixtures, docs and code changes.
2. Run local synthetic tests in an independent ephemeral assistant
   sandbox where available, with the **actual interpreter and
   dependency versions clearly recorded**. Never pass off 3.13 mock
   tests as operator 3.12 or rootless-host verification.
3. Do not use the operational `telmivo` host for MMT verification,
   access credentials, activate APIs or trade without a separately
   justified sandbox boundary and explicit user instruction.
4. If truly device/OS-specific acceptance is required, prefer a
   single minimal operator instruction at the final gate, not repeated
   Termux transcript loops. Keep any blocked gate open otherwise.
