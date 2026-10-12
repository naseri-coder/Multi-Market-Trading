# Stage 16 — Connected offline PAPER preview

**Scope: nonproduction only. Public/LIVE release remains BLOCKED.**

Stage 16 provides an explicitly invoked and reviewable handoff:

Stage-12 owner-scoped core settings and independently selected instrument,
provider, timeframe, allocation and three independent mode requests
→ Stage-6 research metadata validation → Stage-5 synthetic closed-candle feed
→ Stage-7 reviewed Core API strategy evaluation
→ optional Stage-8/9 PAPER risk reservation and unfilled order plan
→ optional Stage-10 **NO-SEND** signal journal.

No new Telegram polling service, real provider, private NYFR source,
credentials, new risk engine, order broker, or public plugin marketplace is
created. A Stage-12 button is **not** a grant to publish or trade.

## API

`OfflinePanelPaperIntegration` accepts an already authorized operator ID,
an existing `OfflineTradingControlCenter`, a reviewed Python strategy core
that provides an exact `CoreManifest`, and an explicit operator ack.

`authorize_paper()` requires an **already configured** Stage-3/8 risk
account/portfolio and exact agreement with the control-plane budget; it
registers the per-instance Stage-8 allocation and pinned bindings without
inventing account equity or loading plugins.

`replay_candles()` requires an exact Stage-12 revision and a bounded,
contiguous, operator-supplied synthetic crypto candle window. It supports
independent analysis, PAPER order-plan creation and Stage-10 dry-run
signal journaling. The target fractions and quantity are explicitly supplied
by the operator. No real or modeled FILL is fabricated by this method.

The Stage-9 close-out still needs explicit `SUBMIT`, `ACK`, `FILL`,
`step_closed_bar` evidence. Exact repeated decisions are idempotent in the
existing Stage-8 and Stage-10 ledgers; altered reused identities are refused.

**Caveat:** Stage-12 and Stage-8/9/10 use different SQLite databases.
This integration is not a durable distributed transaction coordinator.
Panel revision is rechecked, but external authorization must serialize
concurrent settings changes and stop operations. If the second journal
fails, explicitly reconcile the first, then replay identical immutable
evidence under operator control. Do not run as a continuous autonomous
worker. This phase supports **crypto closed-candle** PAPER; FX/index/metal
execution is not misrepresented as completed.

## Reproducible installed-wheel E2E demonstration

Build the existing isolated `multi-market-trading==0.4.0rc1` preview
wheel (not the legacy `crypto-price-action==0.3.2` runtime), install
into Python 3.12 isolated virtualenv, and run:

```bash
MMT_NONPRODUCTION=1 python -m naseri_markets.panel_paper_synthetic_demo_v1 \
  --state-dir "$HOME/mmt-stage16-unique-test" \
  --symbol XYZUSD --timeframe 15m --ack-synthetic-offline
```

This creates a **new** 0700 state directory, separate SQLite ledgers,
synthetic staged instrument metadata and equity, and a **known reviewed
public demonstration core**. It executes two closed candles, creates
Stage-8/9 PAPER risk/order journals, explicitly simulates the next
entry/exit bars via the existing Stage-9 API, records a Stage-10
NO-SEND command, closes/reopens ledgers, and checks Stage-13 integrity.
`--timeframe` supports `5m`, `15m`, and `1h` for this example.

Generated PnL or R is **only a synthetic arithmetic demonstration**.
It does not prove a strategy is profitable. It never sends a Telegram
message or real broker order. Fresh state path is required; rerunning
the same output directory is refused to avoid silently destroying data.

## Verification

The PR's `stage16-offline-panel-paper-e2e.yml` builds a clean wheel
from `platform_release/`, installs it in a disposable Python 3.12 venv,
runs real Stage-3/5/7/8/9/10/12/13 components and tests three operator
timeframe choices. Unit tests cover separate mode toggles, stale revision,
idempotency across signal restart, selected symbol, unsafe path, and
explicit nonproduction authorization.

The standard public unit/full PostgreSQL/Publication Safety workflows
remain independent and mandatory.

## Remaining blocking items

1. Genuine authenticated venue/broker feeds, market sessions, slippage and
   account/external exposure reconciliation.
2. Runtime mounting into real authenticated operator Telegram sessions;
   verified send/edit response and ambiguous-send reconciliation.
3. Transactional recovery coordinator across journals, concurrent
   operator authorization and long-running worker supervisor.
4. Adversarial isolation against third-party code, provenance review and
   independently verifiable market-data PnL/backtests.
5. Production packaging, observability, restore/rollback, KYC/eligibility
   and explicit deployment approval.

**Verdicts:** `STAGE16_OFFLINE_INTEGRATION_TESTABLE` and
`PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE`.
