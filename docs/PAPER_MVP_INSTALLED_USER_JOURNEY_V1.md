# Installed PAPER MVP — Multi Market Trading

**Nonproduction public toy only.** This guide describes a genuinely installed, replayable and restart-readable PAPER sample. It is not a real broker order, Telegram signal, backtest, third-party marketplace, or certified trading strategy.

## Design: reuse an existing authority

The Stage-3 through Stage-15 libraries implement research contracts and separate risk/signal journals but do not form an automatically connected live service. This user journey reuses the existing TrustedLocalCustomHost and its single SQLite permission and PAPER journal. It does **not** build a new order/risk engine, nor does it authorize the universal multi-core runtime.

The new installed **naseri-paper-demo** command accepts only the bundled public toy, which emits an illustrative synthetic signal. Unknown code must **never** be executed through this demonstration. Source hashing protects exact bytes, not code safety.

## Install on a disposable development machine

Use Python **3.12**, a local clone of the public repository, and an isolated user-owned environment, not the server running a trading bot:

~~~~bash
python3.12 -m venv /tmp/mmt-paper-venv
/tmp/mmt-paper-venv/bin/python scripts/a6_prepare_package.py --destination /tmp/mmt-paper-package
/tmp/mmt-paper-venv/bin/python -m pip install /tmp/mmt-paper-package
export MMT_NONPRODUCTION=1
PAPER=/tmp/mmt-example-private-state
/tmp/mmt-paper-venv/bin/naseri-paper-demo --state-dir "$PAPER" init --ack-reviewed-public-toy
~~~~

The destination must be an absolute, previously nonexistent private directory outside the checkout and existing servers. No code executes during init: the bundled demonstration, one synthetic quote, both SHA-256 pins and disabled registration are stored locally.

The JSON returned by init contains **descriptor_sha256** and **revision=1**. Inspect the exact digest and use it to enable the bundled toy explicitly:

~~~~bash
PAPER_CLI=/tmp/mmt-paper-venv/bin/naseri-paper-demo
$PAPER_CLI --state-dir "$PAPER" enable --revision 1 \
  --descriptor-sha256 YOUR_INIT_DESCRIPTOR_SHA256
$PAPER_CLI --state-dir "$PAPER" replay --ack-offline-replay
$PAPER_CLI --state-dir "$PAPER" replay --ack-offline-replay
# Reopen in a fresh process; data is durable:
$PAPER_CLI --state-dir "$PAPER" inspect
$PAPER_CLI --state-dir "$PAPER" disable --revision 2
$PAPER_CLI --state-dir "$PAPER" inspect
~~~~

Expected: first replay = **RECORDED** and one PAPER signal; second replay = **DUPLICATE** and still one signal; journal hash persists over reopen; disable switches permissions OFF but keeps history unchanged. The lower-level [trusted public Custom CLI](TRUSTED_LOCAL_CUSTOM_PAPER_MVP.md) remains available separately for operator-reviewed standalone public code. The guided demo does not accept unknown plugin source.

## Accepted and refused actions

| Request | Behavior |
| --- | --- |
| init without explicit reviewed-toy acknowledgement | Refused without state creation |
| init in an already-existing directory | Refused, no overwrite |
| enable with wrong SHA or old revision | Refused (CAS and pinned metadata) |
| replay without explicit acknowledgement | Refused |
| replay before enable or after disable | Refused |
| LIVE quote or malformed metadata | Refused |
| altered private worker snapshot | Refused on SHA mismatch |
| exact replay of the same signal ID/payload | Idempotent duplicate |
| inspect after process restart | Previous PAPER evidence remains |
| disable | Permission OFF; no journal deletion |

Every operation requires MMT_NONPRODUCTION=1 and refuses MMT_PRODUCTION=1. The CLI never uses a Telegram API, live feed client or broker API. It does not create a second SQLite database or copy the historical PostgreSQL volume; it uses the established custom_paper.db ledger. The output journal SHA-256 is local integrity evidence, not independently attested market provenance.

**Security limitation:** The existing trusted-worker process uses Python -I -S but retains the calling OS user's effective file/network access. It is **not** an isolation sandbox and must not receive unknown scripts, privileged permissions or production credentials.

## CI and readiness

The Stage-15 isolated Wheel smoke test is extended to cover a fresh Python 3.12 installation plus this real toy registration / replay / duplicate / restart / disable path. The repository unit tests exercise stale revisions, missing consent, tampered code, symlink paths and the LIVE-origin refusal. Other project suites run unchanged.

A successful result means **INSTALLED_PUBLIC_TOY_PAPER_MVP_PASS**, *not* an integrated multi-core product, not a strategy edge, and not a production release. The remaining hard blockers in [Stage 15 readiness](PRODUCT_READINESS_AND_RELEASE_GATES_STAGE15_V1.md) persist: authenticated feeds, durable multi-stage handoff, external broker and Telegram evidence/reconciliation, publisher/runsc security review, real risk/position reconciliation, holdout research and deployment/rollback.

The historical **crypto-price-action 0.3.2** runtime and manager remain distinct from the new **multi-market-trading 0.4.0rc1** preview. No legacy runtime, production database, private NY First-Reversal, server, channel or LIVE order was changed or activated.
