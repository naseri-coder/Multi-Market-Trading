# MMT v0.4.0 — Stage 1 source/branch scope freeze and compatibility review

Date: **2026-10-17**. Reference head before this report: `release/0.4.0-candidate@20a05b598bb8c92789925b5af599027a068a225c`.
Evidence: GitHub branch/PR/ref, 57-branch ancestry comparison from the predecessor review, direct original Git tree and selected file reads; **NO integrated build, execution, server, database or source mutation**.

**Decision:** `STAGE1_SOURCE_SCOPE_FROZEN__RUNTIME_ACCEPTANCE_PENDING`.
Target: **`v0.4.0`** (SemVer tag); Python distribution **`multi-market-trading==0.4.0`** (PEP 440). The current source is still **`0.4.0rc1`** and must not be labeled stable before release-commit acceptance.

## A. Public release contract (freeze)

The v0.4.0 candidate is a **new separately installable offline / explicitly operator-enabled PAPER platform**. Its public release is **not** an upgrade/replacement that silently starts the legacy crypto-price-action v0.3.2 production service.

| Surface | Frozen candidate behavior/ownership | Acceptance before v0.4.0 |
| --- | --- | --- |
| Root `pyproject.toml` | `crypto-price-action==0.3.2`, old product and database; keep unchanged | Exact source-integrity check; separate compatibility/rollback; never migrate old database automatically |
| `platform_release/pyproject.toml` | `multi-market-trading==0.4.0rc1`, Python >=3.12,<3.13, empty base dependencies; separate package namespace | Build correct wheel from isolated platform source, update only platform distribution to `0.4.0` at final stage |
| `naseri-markets` | Inert `--check` / `--engine-plan`; no default provider, Telegram or orders | Consistent installed version, valid entrypoint, no network in base CLI |
| `naseri-custom` | Operator-trusted local Custom engine, explicit review and hash pin, PAPER only | Approved-local fixture and state isolation; NO public/untrusted-source execution |
| `naseri-paper-demo` | Bundled synthetic toy PAPER journal | One unique offline state; strict idempotency and recovery; not a claim of profitable strategy |
| `naseri-paper-pilot` | Two-binding Stage20 synthetic pilot, five SQLite ledgers, read-only inspection | Durable restart, receipt and no-double-effect checks; not an authenticated real broker |
| `naseri-engine-admin` | Explicit opt-in DEVELOPMENT Telegram admin | Public channels and actual delivery disabled; no automatic bot launch |
| `naseri-brooks-replay` | Pinned genuine legacy Brooks V5 closed-candle *offline* analysis and modeled PAPER receipts | Verify current 359-file historical source manifest + separate 3 extras; no LIVE |
| `naseri-brooks-market`, `naseri-brooks-kraken-paper` | Separately operator-started read-only public-data polling paths, not automatic base CLI | Provider/region permissions NOT verified; excluded from default startup and accepted offline product path |
| `naseri-brooks-paper-service` | Separate explicitly operator-started development-only worker | Never auto-spawn; signed/approved provider credentials and real account reconciliation NOT accepted |
| Third-party PUBLIC candidate engines | Dedicated admission research/gates only | Untrusted plugin runtime remains **DISABLED** pending verified rootless/gVisor host + authenticated publishing |
| Protected private NY First-Reversal | Metadata reference only, not public source | Keep source code, keys, trained artifacts and private datasets outside wheel, source release and all public docs |

### Database and worker compatibility boundary

- Historical `v0.3.2` manifest contains **348 records**; `main` / current candidate contains **359**. The current candidate manifest Git blob `423169e14e28c33205070edeadb219c4083d79cb` matches `main`, **not** the published v0.3.2 blob `d46ab00e709386beffa3c8d91fb2888084a67f50`. Eight old checksum entries were revised and eleven filenames added since the published tag. This is a **version migration difference**, not permission to rewrite either published tag or current source manifest.
- Maintain the current 359-file manifest/three extra pins verbatim on the candidate; confirm `scripts/verify_runtime_integrity.py` independently on the exact final checkout. Version 0.3.2 old deployments may require a **separate historical runtime and DB**; never attach the new platform to that database by default.
- Old legacy Alembic chain includes post-v0.3.2 revisions 0022/0023. The v0.4.0 package does **not** authorize applying any of these to an existing production DB.
- New platform supports isolated SQLite operator/control and PAPER/evidence stores. Distinct SQLite roles are not a migrated PostgreSQL service, and no automatic replay after ambiguous crash is authorized.
- Base `naseri-markets --check` is intentionally inert. Installed CLI/worker and explicitly operator-enabled data polling must not be described as one background always-on bot.

## B. Review of the 19 independent branch heads

Each row states a **release inclusion decision**, not a judgment that the branch's work has no value. All branch heads remain preserved; zero unreviewed code is blanket-merged.

| Candidate source | Disposition for v0.4.0 | Reason and separate acceptance condition |
| --- | --- | --- |
| `develop/v0.3.0` | **KEEP LEGACY / NO MERGE** | 50 divergent commits relative to R42V in prior compare; old runtime and migration semantics; migrating it wholesale could revert fixes |
| `audit/runtime-a1-data-a1-paper-contract-20261014` | **EVIDENCE ONLY** | Audit docs fork from older branch; reconcile against merged current source |
| `cert-a19-independent-security-research` | **EVIDENCE ONLY / SECURITY OPEN** | Critical publisher fingerprint and real rootless host accreditation unresolved; no claim of CVE/host closure |
| `cert-a19-byte-audit-run` | **EVIDENCE ONLY / SECURITY OPEN** | Extensive offline/hosted research; 7-file gVisor publication byte parity is NOT independent publisher trust or an approved host |
| `feat/stage27-signed-public-intake` | **DEFER EXECUTABLE INTAKE** | Atomically denies execution for public candidates but owner/session authentication, hostile isolation and future onboarding still missing |
| `feature/stage17-authentic-monthly-market-data-custody-v1` | **RESEARCH ONLY** | Genuine historical ZIP evidence is not authenticated contemporaneous venue truth or live access |
| `feature/stage18-primary-funding-mark-btcusdt-2024-01-v1` | **RESEARCH ONLY** | Funding/mark reconstruction and time-of-knowledge uncertain; no broker fee tier or liquidations certified |
| `feature/stage21f-immutable-forward-source-intake-v1` | **PARALLEL DESIGN DEFER** | Conflicting canonical source-admission path with R42 candidate's prospective custody chain |
| `feature/mmt-r26-brooks-decision-economic-parity-audit-v1` | **INDEPENDENT CROSS-CHECK ONLY** | Can audit hypothetical PnL/cost arithmetic; not broker-realized PnL or a replacement for canonical execution |
| `feature/mmt-r38-signed-offline-preview-install-gate-v1` | **SUPERSEDED** | Canonical R38 signed-preview fail-closed path is already in candidate ancestry |
| `feature/mmt-r42-offline-feed-account-evidence-v1` | **PARALLEL AUDITOR DEFER** | Distinct trust authority vs canonical R42C/V/VH; do not merge ambiguous release predicates |
| `feature/mmt-r42-signed-offline-market-account-audit-v1` | **PARALLEL AUDITOR DEFER** | Three Ed25519-signed roles authenticate claimed local inputs, NOT external account or venue; canonical R42 synthetic fail-closed boundary remains |
| `dependabot/github_actions/actions/setup-node-7.1.0` | **DEFER** | Major runner/tool behavior change; job matrix and hashes need independent verification |
| `dependabot/github_actions/actions/upload-artifact-7.0.2` | **CANDIDATE FOR LATER TESTED PICK** | Patch to CI artifact uploader; test upload/download and workflow compatibility first |
| `dependabot/pip/asyncpg-0.32.0` | **DEFER** | PostgreSQL driver transition requires real PostgreSQL 16 integration and wheel/platform closure |
| `dependabot/pip/numpy-2.5.4` | **CANDIDATE FOR LATER TESTED PICK** | Patch; test numerical/float-vs-Decimal economics and lockfile reproducibility |
| `dependabot/pip/ruff-0.17.0` | **DEFER** | Static-analysis baseline/version gate must be rerun, not silently update lockfile |
| `dependabot/pip/sqlalchemy-2.1.4` | **DEFER (HIGH RISK)** | Major-minor ORM/SQL semantic shift; DB integration/migrations and import compatibility not yet tested |
| `dependabot/pip/tzdata-2026.5` | **CANDIDATE FOR LATER TESTED PICK** | UTC/DST, market session windows, region/calendar behavior require time-sensitive regression |

**Bottom line:** 0 of these 19 heads are authorized for a raw merge in the current release freeze. Three small updates may be selected for **new narrowly scoped reviewed PRs after testing**. Public engine execution and actual live trading are explicitly out of scope.

## C. Verified version coupling / release blockers

A direct code search on `main` returned **78 files** referring to `0.4.0rc1`; branch source files read from the release candidate share the same code versions. These references include:

- **Executable modules:** `naseri_markets/platform_cli.py`, `naseri_markets/release_readiness_v1.py`, `naseri_markets/installed_preview_smoke_v1.py`, `naseri_markets/installed_paper_pilot_stage10_v1.py`.
- **Builder/install scripts:** `scripts/a6_release_preflight.py`, `scripts/a6_prepare_package.py`, `scripts/install_platform_dev.sh`.
- **Distribution/build descriptors:** `platform_release/pyproject.toml`, `Dockerfile.platform`, `compose.platform.yaml`.
- **Direct unit contracts:** `tests/unit/test_a6_preview.py`, `tests/unit/test_release_readiness_v1.py`, `tests/unit/test_stage10_installed_paper_pilot_v1.py`.
- **39 workflow references** and historical documentation; historical evidence documents must retain truthful old results rather than blindly search/replace every version string.

**P0 release engineering issue:** simply changing `platform_release/pyproject.toml` to `0.4.0` will cause explicit exact-version refusals in multiple CLI/install/test paths. Before a stable tag, create a reviewed version-transition patch which updates **only the current release executable contracts, installers, build image, relevant tests/workflows and current-facing docs**, preserving historical RC test evidence. The new build/installer must be independently tested in nonroot Python3.12.

**Second P0:** Stage15 declares P0 blockers for authenticated feeds, reconciliation, public messaging and untrusted plugin host. The proposed v0.4.0 scope may be **separately installable OFFLINE / bounded PAPER** only; it must not assert that the whole authenticated multi-market LIVE/public platform is release-ready. Get explicit feature and exclusion decisions reviewed in the release checklist; do not modify hard deny gates to manufacture a PASS.

## D. Mandatory gate for Stage 2

- Resolve version-transition design and tests with one source of truth; no premature `v0.4.0` tag.
- Run clean nonroot actual CPython 3.12 + Ruff including the R42V 59-case pinned suite, integrated full-corpus pytest, PostgreSQL where applicable, wheel build/smoke, malicious/duplicate JSON refusal, PAPER restore/rollback and 32-restart soak on the exact final candidate SHA.
- Preserve historical source checksums, no private engine source, no broker/Telegram real delivery, no server or production DB, and no reliance on GitHub Actions quota for skipped acceptance.
- Verify signed release manifest identity and tested final merged main SHA before any annotated tag.

**Stage 1 completion is SOURCE-SCOPE ONLY**. It does not certify code behavior. Current release verdict remains `V0_4_0_TAG_BLOCKED` until full Stage 2–6 acceptance.
