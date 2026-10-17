# R42-C — canonical offline synthetic evidence auditor selection

**Decision date:** 2026-10-16  
**Scope:** NONPRODUCTION, read-only, synthetic source consolidation only.  
**Parent:** R41 Draft PR #334, head `b4ce088c346c70ffa0feab07cbed807705ed8642`.  
**Selected sibling:** R42 Draft PR #336, head `695ef0aab6992daa6cd00ec960637f6968b912b4`.  
**Not selected as canonical:** alternate R42 Draft PR #335, head `1a0b57f9425114687031f37455d7e8e652c8896e`.

## Explicit decision

Use the **four-input, strictly pinned, synthetic-only data auditor** from #336 as the *single R42 canonical research-source candidate*, subject to independent tests and code review. This is a choice of **one source path**, **not** a production deployment or merging approval. The R42-C branch is based exclusively on the selected #336 head; it does **not** merge sibling #335 or introduce a second provider adapter, ledger authority, release command or strategy engine.

### Evidence-based comparison

| Item | #336 selected synthetic auditor | #335 alternate signed-capture audit |
| --- | --- | --- |
| Common parent | R41 #334 | R41 #334 |
| Market coverage | 2–128 contiguous closed synthetic bars, receipt/time/sequence checks | one signed last-bar snapshot, freshness/spread/tick checks |
| Account comparison | exact balance trio and per-position/per-order IDs, side, contract, quantity and price | primary/review signed snapshots comparing aggregate equity/exposure and order/position **ID lists** |
| Trust proof | four independent caller-provided payload SHA-256 pins, **no cryptographic signer** | three distinct pinned Ed25519 public keys and detached signatures, but **no real venue attribution** |
| External identity | **not authenticated** | **not authenticated by signatures alone** |
| Prior reported tests | 45 assistant-local synthetic PASS on Python 3.13.5, GitHub test suite not run | 47 assistant-local synthetic PASS on Python 3.13.5, GitHub test suite not run |

The #335 signed input schemas and the #336 position-level schema are not directly substitutable. Combining their outputs as if they described one time-coherent real upstream account would be a correctness and assurance error. In particular, distinct *operator-supplied* signer keys do not establish custody by a provider or reconciliation of its remote order book. Keep #335 Draft as **independent research**, with a future separately authorized and specified key-custody/provenance design if needed; **do not** silently transplant signature routines or label them provider-authenticated.

## R42-C discovered defect and bounded correction

Before this patch, #336 required each synthetic account/ledger timestamp to be inside the operator-supplied age window but could accept **otherwise matching values from two different observation times**. The R42-C patch rejects comparison unless the normalized account and local ledger `observed_at` values match exactly. This is a conservative rule for the fixed synthetic v1 schema; it is *not* evidence of an atomic remote capture and does not make operator time trustworthy.

New source denial: `R42_ACCOUNT_LEDGER_TIMESTAMP_DRIFT`. Added unit cases:
- account timestamp differs while all balances, orders and positions match;
- ledger timestamp differs while everything else matches;
- nonmatching timestamp on the command-line path returns refusal.

Previously authored positive and negative unit tests are retained. No schema changes, provider/network calls, credential access, broker routes, public Telegram sends, production data writes or live permissions are introduced.

## Integration and unresolved risks

1. Review the exact diff from #336 into this R42-C branch. The upstream sibling PRs are **diverged** at #334, so never attempt an automatic two-PR merge or count their synthetic passes as one suite.
2. Review and execute the **exact committed** R42 tests (including new denial cases) using clean non-root Python **3.12** with pinned dependencies; run project-targeted lint and regression tests. Previous reports are not a substitute.
3. Recheck the committed source against its Git blob hash, audit path alias/race implications, and confirm the four synthetic inputs are nonproduction-only with immutable independent hashes.
4. Only then propose a nonproduction stacked integration review in topological parent order; no main merge without an explicit separate authorization and broader stack integration proof.
5. Keep the Stage15 **nine P0 + one P1** release blockers open. R41 real rootless/gVisor host acceptance, R27 frozen Brooks true prospective evidence, trusted authenticated provider/feed, trusted account reconciliation and real Telegram delivery are **not** established by R42-C.

## Decision/status matrix

| Gate | Outcome |
| --- | --- |
| Canonical R42 implementation selected | **YES: #336-based source path** |
| Sibling duplicate feature merged | **NO: #335 kept separate Draft research** |
| Synthetic snapshot epoch mismatch patched | **CODE AUTHORED** |
| New committed negative cases run on exact Python 3.12 environment | **PENDING** |
| Whole-stack installed PAPER acceptance | **PENDING** |
| Real broker/provider/account verified | **NO** |
| Real trading, public signal, production release | **HARD DENY** |

**R42-C source consolidation is reviewable, not operationally accepted.** Continue with R42-V exact-committed-source test and integration acceptance; do not proceed to R43 based solely on this PR.
