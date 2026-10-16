# Multi-Market-Trading: bounded roadmap R37–R44 (2026-10-16)

**Status: proposed 8 engineering milestones from the current R36 supply-chain
evidence; R37 STARTED, R38–R44 NOT STARTED.** This is an planning
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
| **R37** | Define canonical signed preview manifest, independent pinned trust anchor and fail-closed Ed25519 verification; no real private key in repo | External key custody/revocation policy, authenticated key fingerprint and Python 3.12 negative tests; signed *preview* only | **STARTED: prototype Draft PR #330, synthetic assistant tests only** |
| **R38** | Installer/release verification integration, fail-closed on missing/bad signatures, rollback behavior | New scratch install + bad key/revoked key/old manifest/replay cases, zero release grants, independent review | PENDING |
| **R39** | One authoritative isolated **PAPER-only** product runtime for config→data→strategy→risk→journal (Stage12→7→8/9→10); strict legacy separation | Audit-quality durable idempotent handoffs and crash/retry contract tests | PENDING |
| **R40** | Clean installed end-to-end PAPER journey plus deferred frozen R27 Brooks full-core evidence; avoid waivers | Fresh disposable install, reset/restart/reconciliation, no connected order or signal, exact Brooks worker acceptance | PENDING |
| **R41** | Disposable independent Linux host hostile plugin tests, real least-privilege containment, secrets/operator identity | Rootless Docker + gVisor adversarial evidence, exfiltration/escape/cleanup and revocation review | PENDING; requires isolated host |
| **R42** | Provider provenance, policy-based eligibility, authentic market feed quality and account reconciliation | Explicit venue/region eligibility, contract ID/data freshness, safe external account/equity/position reconcile without orders | PENDING |
| **R43** | Authoritative Telegram receipt/UNKNOWN reconciliation and durable recovery/rollback/incident rehearsal | Private sandbox delivery acknowledgements and backoff, replay-proof outbox; restore, multi-worker soak, migration dry-run | PENDING |
| **R44** | Independent Stage15 go/no-go audit, research P1 unbiased performance evidence, migration and operational release authority | Each of nine P0 + one P1 independently closed with dated reproducible evidence; real external review | PENDING |

## Counting rules

- **8 named phases R37–R44 inclusive**. R37 is *started but not
  finished*; **7 later named phases remain after R37**.
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
