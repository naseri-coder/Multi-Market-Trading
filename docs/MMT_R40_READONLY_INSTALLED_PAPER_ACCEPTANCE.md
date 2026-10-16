# R40 — Read-only installed synthetic PAPER acceptance (Draft, Brooks deferred)

**R40 does NOT approve a general integrated product, public release or LIVE.**
This fail-closed candidate reuses R39's built-in fixed synthetic two-binding
PAPER journal and the already-existing Stage20/Stage10 offline-only pipeline.
It neither starts a broker nor calls the frozen Brooks worker.

## New inspector and prerequisites

New module: naseri_markets/installed_paper_acceptance_r40_v1.py.

- Requires genuine Python 3.12, non-root, MMT_NONPRODUCTION=1, and no
  MMT_PRODUCTION variable at all; positive operator acknowledgement
  and explicit stop-all-writers acknowledgement are mandatory.
- Requires externally independently reviewed SHA256 pin of installed
  R39 Python module source, installed distribution exactly
  multi-market-trading==0.4.0rc1 with R39 module in its installed-files
  inventory and imported from that installed location. Editable
  installations or mismatching module hash are refused.
- Uses a private owner-only 0700 workspace and six independently-owned
  0600 SQLite files: R39 authority plus the five Stage20 control,
  paper, signals, runtime and effects ledgers. Reject missing,
  symlinked, hardlinked, shared or oversized evidence.
- Computes all six file SHA256 fingerprints, invokes R39 read-only
  reopening **twice** (which independently calls the Stage10
  evidence and Stage9 recovery decision readers), and re-computes all
  six file hashes. Any differing bytes or report, incomplete R39 state,
  broker-positive or LIVE-positive receipt fails closed. Never
  repairs or replays an uncertain job.
- Success-shaped results explicitly keep broker orders, Telegram,
  public/live trading, auto-retry and real market data disabled.
  Brooks full-core remains DEFERRED_R27_FROZEN with independent
  verification false.

The all-writers-stopped boolean is only an operator attestation, NOT
independently proven process isolation. Immutable SQLite read-only
reopening is safe only when writer custody has genuinely been
established on a disposable private test host.

## Critical honest limitations

- Original R34/R36 0.4.0rc1 Wheel was built **before** R39 existed.
  It cannot satisfy the R40 installed-R39 file inventory gate.
  A newly built private Wheel from reviewed R39/R40 source, R36
  byte/RECORD audit and new sandbox installation are required
  before R40 can ever receive a real installed acceptance verdict.
- An externally supplied R39 SHA pin is not real publisher identity
  without independent custody and review. R37/R38 Ed25519 real key,
  revocation source and signing ceremony remain unaccepted.
- R40 does not demonstrate independent host rootless containment,
  real-provider provenance, connected PAPER, multi-database exactly
  once semantics, or availability of any LIVE broker API.
- Frozen R27 Brooks worker smoke failed previously. R40 does NOT
  thaw, edit, rerun against production, waive, or reinterpret R27
  as accepted. The module permanently returns Brooks DEFERRED.
- Existing Stage15 release verdict is
  PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE with 9 P0 + 1 P1
  outstanding gate items. No PR merge/deployment/Telegram messages
  or order routing is performed.

## Authored tests; execution gates

The new test module defines 24 functions (plus parameterized cases)
covering: installed-file inventory and exact independently pinned
module digest, editable/wrong version/missing modules, 6-ledger
byte fingerprint invariance, symlink/hardlink and ownership checks,
missing ledger, R39 inconsistent receipts, PENDING/QUARANTINED
manual recovery, result drift and broker/live refusal, explicit
operator acknowledgements, python-version/nonroot and four
production-variable values, and frozen Brooks negative entitlement.

The test files have been **AUTHORED ONLY**, and **their real pytest
result has not been claimed** for this GitHub branch. The true
non-root Python3.12.3 installed-product verification, an untrusted
fixture crash test under independent host security, clean Wheel
reproduction and frozen Brooks acceptance are still PENDING.

No automation, GitHub Actions, user Termux, or operational Telmivo
host was invoked to pass these tests.
