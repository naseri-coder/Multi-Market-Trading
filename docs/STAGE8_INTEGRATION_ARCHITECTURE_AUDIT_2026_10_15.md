# Stage 8 — Integration Audit & Architecture Freeze

**Verdict: STAGE8_SOURCE_INTEGRATION_AUDIT_COMPLETE — NONPRODUCTION_ONLY / PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE**

**Authoritative evidence baseline:** `main@ff55455285b0eac69ddf4295096e90d28f070243` (2026-10-15).  
**Mode:** Repository source/doc/test inventory and cross-module contract mapping, *read-only evidence review*.  
**Change scope:** This report only. No operational code, requirements, workflow configuration, manifests, database, deployment, public bot, server, or credential change.  
**Verification ceiling:** GitHub content review and file-reference search. No historical market backtest, independent adversarial runtime execution, clean-machine product pilot, private-source review or live-provider attestation was performed for this audit. Existing tests are evidence that tests exist; the audit itself does not claim to have rerun those tests. A PR CI run on this document, if successful, proves only its CI acceptance.

## Executive decision

The public project already has an opt-in **partial integration path**, not merely independent primitives: Stage 12 operator intent → Stage 16 offline replay evaluation → Stage 17 bounded durable queue → Stage 19 pre-call effect-intent records and exact-ID read-only reconciliation → Stage 8/9 modeled PAPER lifecycle → Stage 10 NO-SEND signal journal → Stage 13/18/19 audits. Stage 20 already exercises a bounded **two-binding** synthetic PAPER scenario across these components; Stage 21B runs a captured offline futures research example.

**Do not build a new orchestrator, risk ledger, duplicate broker client, second core registry, or global authority layer.** Preserve the tested Stage-12/16/17/19/20 path as the **single candidate for further PAPER integration**. It is not yet the authoritative commercial or live runtime: five SQLite databases remain non-atomic, Stage-20 pilot cannot safely resume arbitrary crashes, and source/test presence is not proof of external market execution or a profitable edge.

The historical `crypto-price-action==0.3.2` and newer `multi-market-trading==0.4.0rc1` are **different install identities**. Do not relabel, attach or migrate the legacy production database/image as part of the preview. The owner-private NY First-Reversal core is excluded from public packages and this audit.

## Evidence matrix — seven newly delivered modules

`IN_SCOPE_CALLER` means an explicit code call exists among reviewed files, **not** a runtime integration guarantee. `INERT` means standalone library/test/CLI, **not** dead or erroneous code.

| New stage | Source and evidence | Verified reachability in reviewed source | Production/PAPER gap | Decision |
| --- | --- | --- | --- | --- |
| 1: Exchange failures | [diagnostics](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/exchange_failure_diagnostics_v1.py) | `IN_SCOPE_CALLER`: Stage-7 offline MCP calls `diagnose_exchange_failure`. | No authenticated provider error stream or retry/incident policy wiring; output never authorizes retry. | **KEEP** as adviser; do not auto-retry. |
| 2: Order observation | [status normalizer](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/order_observation_normalizer_v1.py) | `IN_SCOPE_CALLER`: Stage-7 offline MCP exposes bounded status translation; reuses existing `execution_contract_v1.OrderStatus`. | No authenticated order stream or Stage-8/9 ledger settlement wiring; cumulative quantity is not an actual fill. | **KEEP**, independent from execution ledger. |
| 3: Fill and fee evidence | [fill contract](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/offline_fill_evidence_stage3_v1.py) | `INERT`: tests and documentation refer to it; no reviewed non-test runtime caller found via code-reference search. | No authenticated execution receipts, fee FX conversion, contract multiplier reconciliation or durable booking. | **KEEP ISOLATED**; *never* book an observed fill without separate authorization. |
| 4: Walk-Forward | [time-fold auditor](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/research_walk_forward_v1.py), [research lab](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/strategy_research_lab_v1.py) | `IN_SCOPE_CALLER`: optional `walk_forward_folds` branch in Stage-11 read-only research. | Audits replayed PAPER outcomes; does not retrain cores or verify independent provider time-series. | **KEEP OPTIONAL**; no edge-certification claims. |
| 5: PBO and DSR | [diagnostic](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/research_overfit_diagnostics_v1.py), [local CLI](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/scripts/mmt_overfit_diagnostics_v1.py) | `IN_SCOPE_CALLER`: independent research CLI and Stage-7 MCP call; not an automatic result of Stage-11 research. | Requires separately prepared, complete simultaneous candidate return matrix and trustworthy experiment inventory; no sealed holdout proof. | **KEEP SEPARATE** until candidate trial provenance is independently verified. |
| 6: Parameter guard | [validated constraints](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/core_parameter_guard_v1.py) | `INERT`: tests/docs refer to its public API; no Stage-12 panel binding/activation caller found. | External trusted schema pins, owner authorization, revisioned persistence and UI integration not in this stage. | **KEEP INERT** until owner-scoped, separately approved Stage-12 adapter. |
| 7: Research MCP | [stdio bridge](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/offline_research_mcp_v1.py), [launcher](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/scripts/mmt_offline_mcp_v1.py) | `IN_SCOPE_CALLER`: opt-in local script exposes stages 1/2/5 and capability listing. Stage-3 fill and Stage-6 settings are intentionally **not exposed**. | No external-client acceptance, no OS sandbox, no deployment; read-only tool metadata is not a security proof. | **KEEP NONPRODUCTION**, do not mount on privileged operator runtime. |

**Interpretation:** The seven modules are additive and do not all form an automatic `1 → 2 → 3 → 4 → 5 → 6 → 7` execution chain. Some are intentionally research-only; their separation is correct, not necessarily technical debt. The missing bindings should be evaluated only when the end-to-end PAPER pilot actually needs them. Source searches cannot independently establish the absence of every possible dynamic import.

## Existing integration graph — ownership freeze

```text
OFFLINE OPERATOR / reviewed public example
     │
     ▼
Stage 12: settings and requested modes (NOT authorization to trade)
     │          ▲
     │          └── Stage 6 parameter guard: future reviewed schema pin bridge only
     ▼
Stage 16: closed-candle offline orchestration
     │
     ▼
Stage 17: explicit, bounded queue; PENDING / CLAIMED / DONE / QUARANTINED
     │
     ├── Stage 19: committed pre-call effect intents
     │         └── Stage 19 exact-ID read-only reconciliation (no auto retry)
     ▼
Stage 8/9: simulated-risk/order/position PAPER ledgers
     │
     ├── Stage 10: NO-SEND signal journal
     └── Stage 13/18/19: read-only reconciliation and integrity audit
                │
                └── Stage 20: two-binding synthetic acceptance journey
                         │
                         └── Stage 21B: narrower captured-data PAPER fixture
                               (upstream authenticity/venue economics unverified)

STAGE 11: read-only PAPER research → Stage 4 optional time-purge audit
STAGE 5: standalone multi-candidate PBO/DSR diagnostics ← Stage 7 MCP
STAGE 1/2: manual diagnostics ← Stage 7 MCP
STAGE 3: bounded, independent fill evidence (NO BOOKING)
STAGE 7: local stdio-only MCP, no Production tools
```

**Single-owner recommendation:** Stage 12 owns *operator intent*, Stage 16 owns reviewed offline *handoff*, Stage 17 owns *work scheduling / local claim*, Stage 19 owns *effect-intent evidence and exact-ID matching*, Stage 8/9 owns *PAPER economic ledger*, Stage 10 owns *NO-SEND signal state*, Stage 11/4/5 own *research calculations*. Do not make the MCP bridge, parameter guard or status normalizer an authority to change positions, send Telegram or approve retries.

Existing proof: [Stage-16 contract](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/OFFLINE_PANEL_TO_PAPER_STAGE16_V1.md), [Stage-17 supervisor](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/OFFLINE_RUNTIME_SUPERVISOR_STAGE17_V1.md), [Stage-19 intents](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/job_effect_intent_v1.py), [Stage-19 exact-ID matcher](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/job_effect_reconciliation_v1.py), [Stage-20 candidate](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/UNIFIED_PAPER_PILOT_STAGE20_V1.md).

## Findings ranked by severity and evidence

### P0 — Blocks claiming end-to-end durable PAPER reliability

**S8-F01 — Multi-ledger crash ambiguity, CONFIRMED DESIGN GAP.** Stage 20 documents **five separate SQLite stores** and no distributed ACID or global exactly-once guarantee. Stage 19 *already* commits `PREPARED` before downstream effects and offers an exact-ID reconciler. Thus the real unresolved issue is not a missing reconciler; it is crash-safe ownership of ambiguous `PREPARED`/target-record/receipt gaps across multiple independent commits. On a failure after a target write and before the receipt, the existing rules appropriately **block automatic retry**. Evidence: [pilot](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/UNIFIED_PAPER_PILOT_STAGE20_V1.md), [intent ledger](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/job_effect_intent_v1.py), [matcher](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/job_effect_reconciliation_v1.py).

**S8-F02 — Authoritative product journey is still a scoped demo, CONFIRMED RELEASE BLOCKER.** Stage 20 uses a built-in illustrative fixture and requires a fresh directory; Stage 17 is operator-invoked, not a continuously running authenticated service. A clean-installed preview demo is useful, but it is not proof of real owner-panel remote authentication, live data, actual Brooks Core API adapter, restart/recovery under adversarial concurrency or public rollout. Evidence: [Stage 20](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/UNIFIED_PAPER_PILOT_STAGE20_V1.md), [Stage 15 readiness](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/PRODUCT_READINESS_AND_RELEASE_GATES_STAGE15_V1.md).

**S8-F03 — Product identity / authority split, CONFIRMED PACKAGING FACT.** Root [`pyproject.toml`](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/pyproject.toml) names `crypto-price-action==0.3.2` while [`platform_release/pyproject.toml`](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/platform_release/pyproject.toml) names `multi-market-trading==0.4.0rc1` and currently specifies an empty main dependency list. This is a deliberately distinct distribution, not proof of a migration defect. Explicitly select a pilot installer and validate *its actual dependency closure* before claiming a unified installation. Do **not** mutate the legacy manager, DB or package as an implicit cutover.

### P1 — Needed before making authenticated-data, economic-performance or operator-UI claims

**S8-F04 — Stage-2/3 data-to-ledger seam, UNIMPLEMENTED IN REVIEWED PATH.** No reviewed non-test caller joins `OrderObservation` and `FillEvidence` to Stage-8/9 authenticated PAPER effects. That is appropriate under the current no-live architecture. No future bridge may treat a cumulative `FILLED` status or a vendor execution fixture as settlement proof; it must preserve account, instrument, contract-unit, fill ID, currency, fee direction and authenticated execution-source provenance. Evidence: [Stage 2](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/ORDER_OBSERVATION_NORMALIZER_STAGE2_V1.md), [Stage 3](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/OFFLINE_FILL_FEE_EVIDENCE_STAGE3_V1.md).

**S8-F05 — Core-parameter owner/revision bridge, UNIMPLEMENTED IN REVIEWED PATH.** Stage-6 validator is a pure helper; Stage-12 settings store does not yet call it. External **host-trusted** schema SHA pin and owner approval cannot be replaced by a self-supplied checksum. Future UI change requires an independently scoped, fail-closed Stage-12 adapter; it must preserve `LIVE` denial and the existing revision fences. Evidence: [guard](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/CORE_PARAMETER_GUARD_STAGE6_V1.md), [panel](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/trading_control_center_v1.py).

**S8-F06 — Research provenance and bridge, CONFIRMED METHODOLOGY LIMIT.** Stage-4 audits PAPER outcomes rather than rerunning/retraining a strategy. Stage-5 consumes a separately prepared candidate-return matrix and cannot independently prove all failed historical trials were included. Stage-21B captured-data provenance and Stage-21F same-provider evidence do not establish independent provider authenticity or complete real futures economics. Never publish a real backtest/edge claim from synthetic pilot statistics. Evidence: [Stage 4](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/RESEARCH_WALK_FORWARD_STAGE4_V1.md), [Stage 5](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/RESEARCH_OVERFIT_DIAGNOSTICS_STAGE5_V1.md), [Stage 21F](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/market_evidence_gate_stage21f_v1.py).

**S8-F07 — External operator/security boundary, UNVERIFIED FOR RELEASE.** Stage-7 MCP is a local stdio tool bridge, not externally certified with all clients and not an OS sandbox. No authenticated Telegram send/read-back, broker/futures account eligibility, secrets-management rehearsal or hostile third-party plugin isolation is established by its presence. Stage-40 host readiness remains an evidence gate, not a deployed host measurement. Evidence: [Stage-7](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/OFFLINE_RESEARCH_MCP_STAGE7_V1.md), [Stage-40](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/offline_host_readiness_stage40_v1.py), [readiness](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/PRODUCT_READINESS_AND_RELEASE_GATES_STAGE15_V1.md).

### P2 — Improve clarity; do not create new infrastructure solely to close them

**S8-F08 — Historical roadmap and package presentation.** Root `ROADMAP.md` still describes a v0.3.0 readiness track despite a separate v0.4.0rc1 preview. A focused future documentation update should clearly distinguish the legacy path, the approved PAPER candidate, research-only tools and externally blocked capabilities. This is **not** a reason to relabel the root package. Evidence: [roadmap](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/ROADMAP.md), [README](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/README.md).

**S8-F09 — Nonproduction evidence coverage is partial by design.** Stage 20 verifies initial `PAPER_RESERVE`, `PAPER_PLAN` and `DRY_SIGNAL` intents but not every later modeled fill/exit; the clean-wheel smoke and independent tests cover different paths. Treat coverage statements literally and don't claim a single, complete, installed real-order test. Evidence: [Stage 20](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/docs/UNIFIED_PAPER_PILOT_STAGE20_V1.md), [Stage 19](https://github.com/naseri-coder/Multi-Market-Trading/blob/ff55455285b0eac69ddf4295096e90d28f070243/naseri_markets/job_effect_intent_v1.py).

## Architecture freeze — authorized current role

| Element | Authoritative research-owner | Must not be promoted as |
| --- | --- | --- |
| Owner/requested parameters | Existing Stage-12 operator intent, host-pinned Stage-6 schema guard **not yet wired** | Credential vault, automated strategy activation |
| Job lifecycle | Existing Stage-17 durable queue | Multi-host exactly-once executor |
| Cross-ledger evidence | Existing Stage-19 intents / exact-ID read-only reconciliation, backed by Stage-18 review | Atomic transaction or auto-retry license |
| PAPER money state | Existing Stage-8/9 risk, order, position ledgers | Authenticated broker account settlement |
| Signal state | Existing Stage-10 local NO-SEND journal | Verified Telegram delivery |
| Diagnostic execution | Existing Stage-1/2/3 bounded observations | Trading action, position posting or price conversion |
| Research outputs | Stage-11 plus optional Stage-4 and standalone Stage-5 diagnostics | Verified strategy edge or real profitability |
| MCP | Stage-7 opt-in, local, static allowlist | Privileged control plane / plugin sandbox |
| Distribution | `platform_release` v0.4.0rc1 preview | Historical root package migration |

**Freeze rules:** no auto-enable; no exchange credentials; no live venue/Telegram access; no `NY First-Reversal` public source; no source/manifest/risk threshold changes under this audit. Hashes are reproducibility markers, not proof of custody, provenance or authorization.

## Stage 9 — precise proposed next implementation contract (NOT AUTHORIZED BY THIS REPORT)

**Recommended title: STAGE9_CROSS_LEDGER_RECOVERY_EVIDENCE_CLOSURE_V1**

**Goal:** Address **S8-F01** on the *existing* Stage-17/19/18/20 path, not introduce an eighth ledger or independent executor. Preserve the current `PAPER_RESERVE`, `PAPER_PLAN`, `DRY_SIGNAL` exact ID and receipt contracts.

**Proposed implementation order, subject to separate approval:**

1. Pin `main` and capture Stage-17/18/19/20 golden fixture baselines and hashes; specify the canonical `job_id → expected effect IDs → target receipt identities` map and which transitions are atomic within a single database (never claim atomicity across five).
2. Build a bounded **read-only** multi-ledger decision table on consistent private nonproduction snapshots, reusing the Stage-19 matcher and Stage-18 reports. Distinguish: `EXACT_TARGET_AND_RECEIPT`, `TARGET_EXISTS_RECEIPT_GAP`, `PREPARED_NO_TARGET_UNKNOWN`, `TARGET_CONFLICT`, `AMBIGUOUS_SIGNAL_OUTBOX`, `MISSING_JOB`. Default ambiguous or invalid states to `BLOCKED_OPERATOR_REVIEW`.
3. Define an explicit operator-led, **fail-closed** recovery protocol: stop every potential writer, take owner-private snapshots, inspect exact IDs and receipt digests, quarantine unknowns. No automatic retry, queue stealing, ledger repair, irreversible deletion, or creation of synthetic receipts.
4. Extend disposable Stage-20 tests for crash cutpoints before/after prepared intent, before/after each local target commit and receipt commit, concurrency and restart; assert **no duplicated PAPER effect, no unreported ambiguous effect, and no live/Telegram send**. Do not weaken current tests or hidden release fences.
5. If a small source change is strictly necessary, limit it to the existing Stage-18/19 reconciliation/fixture surfaces and their exact tests; define a separate PR and require full protected CI. If only evidence tests/documentation are necessary, do not add another library layer.

**Acceptance:** a complete, executable negative-case matrix in isolated copies; stable reason codes and evidence digest; operator-visible blocked outcomes; no loss or duplication in the tested modeled PAPER effects; no widening from nonproduction. **Do not claim cross-DB ACID or global exactly-once**. Any later transactional redesign or automatic recovery is a separately authorized project.

**Stop gate:** Stage 9 does **not** start under Stage 8 permission. No later stages, new PRs, deployment, source change, non-public file reads or operational modification are authorized by publishing this audit.

## Stage-8 completion checklist

- [x] Pin source baseline and examine README, existing release/readiness audits, Stage-12/16/17/18/19/20/21 and seven new modules.
- [x] Locate explicit in-repo call references for seven new modules and classify independent vs actual calls.
- [x] Map current candidate PAPER ownership and avoid duplicating Stage-17/19 mechanisms.
- [x] Record evidence-backed P0/P1/P2 findings without claiming a live reproduction of hypothetical failures.
- [x] Specify exact narrow acceptance contract for a future Stage-9 implementation.
- [x] Keep all existing code, databases, manifests, secrets, workflows and Production unchanged.
**Publication verification:** The documentation PR and its protected checks are tracked in GitHub PR metadata; a successful docs-only PR is **not** a new runtime acceptance test or an operational permission.

**Final audit state:** `STAGE8_INTEGRATION_ARCHITECTURE_FREEZE_PASS__RELEASE_BLOCKED`. The first clause means the reviewed architecture and next repair boundary are documented, not that every independently authored module has been installed, run or exercised end-to-end.