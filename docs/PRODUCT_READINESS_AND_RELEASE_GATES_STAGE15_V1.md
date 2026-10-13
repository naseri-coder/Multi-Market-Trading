# Multi Market Trading — Stage 15: Final Product Readiness & Controlled Release Gates

**Baseline:** `main@7c463830d79fe37f6dde18476dc60cfff37ad8b6` (Stage 14).  
**Scope:** one additive, nonproduction, read-only release preflight; one clean-wheel, synthetic strategy smoke; a targeted CI job and tests. No server, legacy runtime, Docker deployment, token, signal channel, exchange, private custom core, production database or API is changed. This stage **does not claim the actual product is release-ready**.

## Executive release decision

**`PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE`**. The public repository has valuable offline contracts, PAPER journals and developer test utilities, but does not have a single authenticated production-ready runtime that joins panel, market data, strategy evaluation, risk, order execution, and public Telegram delivery. Stage 13's handoff remains manually injected; Stage 12 toggles are intent only. Stage 14 static review and signatures do not prove that hostile third-party Python code is contained. The historical root `crypto-price-action==0.3.2` runtime, `markets.sh` and the separate `multi-market-trading==0.4.0rc1` **preview** are distinct identities.

No automated source audit is allowed to grant a release entitlement. `evaluate_source_readiness()` has only a read-only source completeness/identity preflight and a **permanently negative operational release verdict**. A human/security/operations-led release process would require separately scoped future implementation. A clean wheel smoke validates only installation and one known harmless synthetic strategy decision, never network delivery or real venue readiness.

## Implemented paths

- `naseri_markets/release_readiness_v1.py`: bounded, read-only static completeness/identity checks; SHA256 evidence fingerprint; explicit open blockers with priorities. No dynamic import of unknown code and no `exec`, DB write or network. All release authorizations permanently false.
- `naseri_markets/installed_preview_smoke_v1.py`: a deterministic, **known trusted example only** Core API → Stage 5 market feed → Stage 7 strategy orchestrator smoke on two synthetic 15m candles. Requires installed `multi-market-trading==0.4.0rc1` and explicit isolated-nonproduction acknowledgement; returns validated decision, **never** an order or Telegram message.
- `scripts/mmt_stage15_readiness.py`: separate read-only CLI requiring `MMT_NONPRODUCTION=1` and `--ack-source-audit`. Exit 0 = source preflight successful, **not approval**; exit 1 = missing expected source, exit 2 = unsafe input or missing explicit fence.
- `tests/unit/test_release_readiness_v1.py`: denial, metadata drift, missing module, symlink, malformed files, size, fingerprint, CLI and no-grant tests.
- `.github/workflows/stage15-clean-preview-gate.yml`: single focused PR job: static source preflight + unit tests + build an **isolated copy** of the official platform wheel, install in a clean Python 3.12 venv and test the synthetic Stage-7 decision outside the repo tree. No database, Telegram token or broker credentials; no write to main/deploy. This is supplemental to existing CI, not a repeated full test corpus.

## Reproducible read-only source preflight

```sh
MMT_NONPRODUCTION=1 python -m scripts.mmt_stage15_readiness \
  --repository . --ack-source-audit
```

`source_verdict=SOURCE_PREFLIGHT_PASS` means only that expected source paths and version separation exist. The `release_verdict` will **still be** `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE` and all publication/plugin/deployment/live-order permissions will be `false`. A source audit does not attest an actual installed wheel. Avoid feeding the CLI any production data or secrets; it does not need them.

For the installed wheel, use a **fresh isolated 3.12 virtual environment** on a disposable nonproduction machine. Build from a copied `platform_release` project tree containing only `pyproject.toml`, `README.md`, and the reviewed public `naseri_markets/` directory; install the resulting wheel with `--no-deps`; invoke from outside the checkout:

```sh
MMT_NONPRODUCTION=1 python -m naseri_markets.installed_preview_smoke_v1 --ack-isolated-preview
```

Only the known `OfflineContractFixture` synthetic fixture is evaluated in process. Never substitute an external developer core or real broker credentials for this smoke.

## Severity-ranked release blockers

| Priority | Gate | Required independent evidence for closure |
| --- | --- | --- |
| P0 | One authoritative integrated runtime | Authenticated, fenced and durable Stage12→7→8/9→10 handoffs, failure recovery and operator audit |
| P0 | Clean installed **end-to-end** user journey | Verified install → config → data/replay → PAPER journal → restart/reconcile → query under a single selected product path |
| P0 | Release authority / migration | Deliberate one-way cutover strategy separating legacy v0.3.2 DB, namespace, image and root installer from v0.4 preview |
| P0 | Provider and account eligibility | Real upstream identity, policy-based provider allowlist by actual residency and instruments, active account/position reconciliation |
| P0 | Telegram delivery | Private-channel authentication, authoritative delivery/read-back and edit acknowledgements, UNKNOWN handling, rate limits |
| P0 | Hostile plugin containment | Disposable rootless Docker + gVisor independent adversarial test and resource/escape/cleanup review |
| P0 | Secrets & access | External credentials, real Telegram admin authentication, secret rotation/revoke and safe incident isolation |
| P0 | Recovery & operations | Migration dry run, durable replay IDs, backup/restore, concurrency soak and rollback rehearsals |
| P1 | Research claims | Non-cherry-picked authentic data, pre-registered true holdout, sufficient samples and cost stress; no unsupported edge claims |

## Supported release lanes

1. **Offline source and wheel smoke:** eligible for limited nonproduction demonstration if the source/wheel preflight checks pass; no user deployment is performed by this stage.
2. **Installed private PAPER pilot:** still blocked as a unified Stage 12–Stage 10 product; prepare only after a separately approved implementation of the first four P0 gates and clean-room operator acceptance.
3. **Public signal bot:** blocked pending independently verified provider, channel read-back, idempotent delivery and operations evidence.
4. **Marketplace / third-party Python core execution:** blocked until human security review, publisher chain of trust, hardened isolation and approved installation controls.
5. **LIVE broker order execution:** blocked; separate compliance, real broker specification, account safety and incident/reconciliation program is required.

## Governance & next decision

**Do not call this `PRODUCT_READY`, do not widen any venue sanctions/KYC allowlist, and do not enable a token, publisher, poller or real broker endpoint.** The next actionable scope should be one narrowly designed installed **PAPER-only pilot** with a single authoritative runtime path and operational evidence, not an open-ended security framework program. A feature-stage CI pass is only a software-test result.

NY First-Reversal remains OWNER_ONLY: no private source, binary, encrypted public package, path disclosure or commercial distribution is authorized.
