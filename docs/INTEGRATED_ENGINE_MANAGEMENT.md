# Multi Market Trading — Integrated Engine Management (Nonproduction)

**Purpose:** Finish user-facing management in the NEW product Telegram application
with three separate engine categories, per-engine settings, and accurate runtime
status. This does **not** deploy to the running historic crypto signal bot.

## Exact engine classification

| Engine | Category | Visible to | Can the new PAPER host execute it? |
| --- | --- | --- | --- |
| Public trusted locally reviewed Python engine | `PUBLIC_CUSTOM` | Administrators | **Yes**; explicit SHA-pinned local code and PAPER only |
| Al Brooks Price Action (`brooks_price_action`) | `BUILTIN_BROOKS` | Administrators | **Yes for explicit manual offline candle replay**; new bot does not launch it autonomously |
| NY First-Reversal (`ny_first_reversal`) | `OWNER_CUSTOM` | Explicitly provisioned owner IDs only | **No**; private metadata **reference only**, source, private repo, binaries and encrypted payload never included |

Brooks is an internal named engine, **not** an arbitrary public third-party
Custom plugin. NY First-Reversal is classified as an owner **Custom** engine,
but public users, non-owner administrators, the public plugin list, the
public installer and downloadable assets must never discover or install it.
Only a pre-authorized owner may create its **private local metadata reference**
with `--owner-reference`; NO private code or artifact is ever loaded.

### Meaning of enabled / disabled

- Public trusted Custom: enabled/disabled controls the real local PAPER
  execution permission, with SQLite revision CAS and admin audit in the
  SAME transaction as the permission flip.
- Brooks and owner-only Custom: enable/disable records only **requested
  enablement**. The UI always says `RUNTIME_NOT_MOUNTED` and shows
  `enabled=False` for both, even if the requested toggle is on. This is
  NOT runtime dispatch, strategy activation, signal generation, or a claim
  that the existing Brooks production bot was reconfigured.
- No actual engine code is copied out of `production_source/`.
  Its SHA256 manifest, existing working bot and databases are unchanged.

## Per-engine Telegram admin settings

In the private admin Telegram chat, use `/engines` (or `/custom`). Every
engine has its own:
- requested or real PAPER enable/disable button with revision fencing;
- **timeframe preference** (1m/5m/15m/1h/4h/1d), **market scope** (all/crypto/
  forex/index/metal), and **signal environment** `OFF` or `PAPER`;
- separately verified private channel ID and delivery route; ALWAYS
  `DISABLED` for automatic channel delivery, even if the bot has posting
  rights;
- private-admin-only recent PAPER preview, and per-engine audit history.

The PAPER and market settings for a genuinely installed **public Custom**
engine are checked by the local execution host both **before worker
invocation** and **under the same SQLite writer transaction that persists
the PAPER result**. Settings updates cannot race past final commit.
The timeframe preference is **not applied to a quote**: the current A7
single-tick request has no validated timeframe field. For Brooks, PAPER, timeframe and market-scope settings now also gate the
explicit local OFFLINE replay worker. Brooks is **not** yet continuously
running or receiving live feeds. For owner Custom, settings remain metadata
until its private owner-side runtime is separately connected.
No secret threshold/strategy tuning in the legacy core is performed.

Owner-only engine references remain hidden from the shared panel to other
administrators, even if they know their engine ID and manually forge a
callback. The owner ID must also be explicitly listed as an administrator.
Telegram channel configuration uses the existing verified private-channel
getChat/getMe/getChatMember flow; **no** SendMessage/channel publish is
called. Stored channels are not used for automatic PAPER delivery.

## Actual next-product Telegram Application bootstrapping

`naseri-engine-admin` is a third explicitly allowlisted CLI included in
the isolated new `multi-market-trading==0.4.0rc1` release. It mounts
`IntegratedEnginePanel` into **ONE python-telegram-bot Application**.
No parallel polling is started by import, build or `--check`.

### Read-only-style local check (no Telegram network)

```bash
naseri-engine-admin --state-dir /tmp/mmt-custom-state \
  --admin-ids 123456789 --owner-ids 123456789 --check
```

This prints non-secret readiness flags and visible public/built-in counts.
Owner reference creation is **explicit**, and does not occur on check.

### Optional independent DEVELOPMENT bot, never use production credentials

Only in an explicitly authorized non-production test environment with a
**different development bot token**:

```bash
export MMT_NONPRODUCTION=1
export MMT_DEV_BOT_TOKEN='<dedicated DEVELOPMENT BotFather token>'
naseri-engine-admin --nonproduction-poll \
  --state-dir /tmp/mmt-custom-state \
  --admin-ids 123456789 --owner-ids 123456789 \
  --owner-reference
```

`--owner-reference` seeds the owner-private **NYFR identity only** in local
metadata (no script, strategy, plugin, private GitHub repo, encrypted code,
license or binary). The owner ID is not a globally discoverable public
catalog entry. The state directory must be private (0700).

Startup refuses to poll unless BOTH the explicit CLI switch and
`MMT_NONPRODUCTION=1` plus a dedicated `MMT_DEV_BOT_TOKEN` are present.
Do not run a second poller for an already deployed bot token.

### Integrating with an existing product Application

Alternatively:

```python
from naseri_markets.integrated_engine_panel import IntegratedEnginePanel

panel = IntegratedEnginePanel(
    state_dir="/private/path/to/custom-state",
    admin_ids={ADMIN_USER_ID},
    owner_ids={OWNER_USER_ID},
)
panel.register(existing_application)
# start this existing Application only in an authorized environment
```

This preserves the legacy bot's application and source manifest. Attaching
it to the **already live** production bot still requires an explicit
deployment authorization; code-level startup exists only for the new
isolated product.

## CI acceptance and honest residual work

CI checks actual clean installed wheel/optional `[telegram-admin]` dependency,
single-Application mounting, `/engines` and `/custom` commands, owner
non-disclosure, Brooks visibility and nonexecution, per-engine revisioned
settings, disabled routes, real public Custom OFF/market gating, PAPER
signals and legacy tests. All of it runs WITHOUT any live Telegram message
or broker order. Production source hash/publication safety is preserved.

**Remaining work (NOT silently implemented here):**
- A **real manual offline Brooks V5 replay adapter now exists**, with
  causal closed-candle validation, genuine engine evaluation, SQLite PAPER
  output and admin preview. Automatic bot-cycle dispatch, real market feeds,
  and authenticated FORWARD publication are still missing. This adapter
  intentionally does not migrate or modify the frozen source.
- NYFR requires its own private, owner-only executable adapter / licensing
  outside the public repository. **It is never publicly installable, even
  encrypted or compiled**.
- Authentic live-feed signal delivery to channels needs an independently
  tested authenticated FORWARD pipeline and explicit operator authorization;
  PAPER previews are not channel signals.

**Target verdict:** `INTEGRATED_PUBLIC_CUSTOM_BROOKS_OWNER_PANEL_READY_NONPRODUCTION`.


## Follow-up: real Brooks manual offline replay (public)

The next standalone CLI, `naseri-brooks-replay`, checks the frozen legacy
manifest and invokes the real Brooks full-core V5 evaluator in a separate
process. It consumes bounded historical closed-candle windows and records
eligible PAPER decisions or an explicit NO_SIGNAL scan. It uses the existing
Brooks per-engine requested-enable flag, PAPER mode, market scope and
selected timeframe, rechecking configuration inside the SQLite transaction.
The Telegram admin panel shows PAPER signals and replay/no-signal counts.
The main Telegram bot **still does not automatically run Brooks**; no
channel delivery is enabled. See [Brooks real Replay/PAPER guide](BROOKS_REAL_OFFLINE_PAPER_REPLAY.md).
