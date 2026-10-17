# R39 — Durable, single-fixture authoritative PAPER journey (Draft)

**STATUS: implemented as a bounded code/test candidate, acceptance PENDING.**
This is an *offline synthetic* durable coordinator for the existing
Stage12→Stage17→Stage20→Stage10 chain. It does **not** certify a
general multi-user trading runtime or close Stage15's
P0_SINGLE_INTEGRATED_RUNTIME blocker.

## Existing modules reused, not duplicated

- Stage12 control panel with explicit snapshot/revision: existing
  OfflineTradingControlCenter in the Stage20 pilot.
- Stage7 data/replay and known public synthetic Core API fixture,
  Stage8 PAPER risk bridge, Stage9 effect/outbox bookkeeping and
  Stage10 PAPER lifecycle are already exercised by existing
  unified_paper_pilot_stage20_v1.run_paper_pilot.
- Stage10 installed_paper_pilot_stage10_v1.inspect_installed_paper
  supplies *independent read-only after-stopping-writers* SQLite
  reliability and effect reconciliation. It does not authorize broker
  access or assume automatic recovery.

New module: naseri_markets/offline_authoritative_paper_journey_r39_v1.py

## Durable authority and trust boundary

R39 runs **only** an exact built-in two-binding example using
BTCUSD/5m and ETHUSD/15m with existing synthetic provider data,
recognized test-only Core API fixture, and fixed budget allocation.
It does not load an unknown plugin or fetch a real feed.

Before Stage20 starts it creates a new operator-owned 0700 private
workspace outside the operational environment and exclusively
creates a 0600 SQLite authority.sqlite (DELETE journal,
synchronous FULL, transaction under BEGIN IMMEDIATE). Exactly one
fixed fixture request SHA256 is written at status **PENDING** and
committed *before* invoking any downstream PAPER component. It
never takes a client-supplied account, exchange URL, Telegram token
or strategy code.

After Stage20 reports two completed jobs and two closed modeled
PAPER positions, R39 checks fixed expected source, binding IDs,
timeframes, modeled PAPER-only flags and Stage20 blocked-release
verdict, then **calls the real Stage10 reopen-only checker** after
all Stage20 writers have returned/closed. Stage10 independently
checks database owner permissions, two runtime jobs, Stage9 effect
receipts, risk ledger and source-denied PAPER disposition.
Only after all independent checks match does R39 commit a canonical
report and evidence digests with status **DONE**.

An exception after a job intent has committed becomes
**QUARANTINED** (if the process remains alive). If the process is
killed before marking a decision, the durable record stays
**PENDING**. On either state **no automatic restart or resubmit** is
permitted: partial cross-DB commits could exist. This design
does NOT prove cross-database transaction atomicity or true
end-to-end exactly once semantics.

A separate operator-confirmed, all-writers-stopped inspect()
uses SQLite mode=ro&immutable=1 and Stage10 read-only reopening
to detect mismatches in recorded requests/reports, downstream
effect receipts and reliability fingerprints. No replay or repair is
performed. The CLI exposes exactly --run-new and --inspect; there
is no --resume, --retry, --repair, --live or --publish option.

R39 requires Python 3.12, MMT_NONPRODUCTION=1, absence of
MMT_PRODUCTION, explicit operator acknowledgement, **non-root UID**,
and a private owner-controlled parent directory. Unit tests under
root use an explicitly mocked outer R39 gate only; that is **not**
proof of real nonroot OS containment.

## Tests authored for real Stage20/Stage10 and failure cases

tests/unit/test_mmt_r39_durable_synthetic_paper_authority_v1.py
contains 17 test functions / **20 collected cases** including:

- One *unmocked* Stage20/Stage10 synthetic integration journey;
  test-only bypass of the outer R39 non-root requirement.
- Durable completion and exact same-job duplicate refusal.
- Read-only reopening with unchanged SQLite bytes.
- Simulated downstream crash after a partially created pilot
  directory: QUARANTINED, no automatic replay and no delete.
- Interrupted post-effect pre-DONE transaction represented by
  PENDING: no reprocessing or automatic claim recovery.
- Broker-order-positive report refusal and quarantine.
- Source request drift, report corruption and Stage10 digest drift.
- No-signals variant, incorrect ack and inappropriate world-readable
  or symlinked workspace.
- Four explicit production environment variable values and
  missing operator ack; CLI run vs inspect mode controls.

These tests were **authored in GitHub** but have not been
executed in the user's Python 3.12.3 PRoot or in an independently
qualified host as part of this R39 turn. No claim of 20 PASS is
permitted without actual pytest output. GitHub Actions must not be
triggered simply to gain a test badge while quota is constrained.

## Release denial and remaining blockers

Passing the test-only R39 scenario would be a meaningful durable,
fail-closed synthetic handoff, but **not** a general authenticated
dispatcher. Source/provider, real account identity, production
secrets, unknown external cores, owner-only NYFR, frozen Brooks,
private Telegram and actual broker execution remain untouched.
The Stage15 software verdict is still
PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE with **9 P0 + 1 P1**
independent release blockers. R27 frozen Brooks full-worker smoke
is still deferred.

No merge to main, production changes, connected PAPER, LIVE,
public Telegram, provider API, independent publisher signing key,
real account credential or operational Telmivo server use was
performed. The next R40 pilot should obtain genuine disposable
nonroot Python3.12 integration and recovery evidence, **without**
calling R39's synthetic result a product release certificate.
