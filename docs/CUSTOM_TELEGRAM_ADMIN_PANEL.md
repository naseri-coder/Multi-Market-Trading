# Multi Market Trading — Telegram Custom Engine Admin Panel (optional integration)

**Scope:** Complete *code-level* operator panel for the trusted LOCAL Custom
PAPER host. GitHub source/CI only; **NOT ACTIVATED on any running Telegram bot**.
The historical production bot under `production_source/` is intentionally
frozen with its own source SHA256 manifest. No production server, database,
bot token, channel, Telegram post or trading engine has been modified.

## What the operator can do inside Telegram

- Open `/custom` or the admin keyboard button
  `🎛 مدیریت هسته‌های Custom` in a **private chat** with the owning bot.
- View registered public Custom engines, versions, real enabled/disabled
  state and CAS revision, PAPER signal counts and pinned descriptor digest.
- Enable or disable one engine on the same SQLite database used by the
  genuine trusted local Python Custom worker. Every toggle increments its
  revision and writes an administrator audit entry in the **same transaction**.
  Stale duplicated button presses fail closed.
- Configure or clear a **different private Telegram destination per engine**.
  When setting a channel, provide its numeric `-100...` Telegram ID. The
  panel queries `getChat`, `getMe` and `getChatMember` to ensure it is
  a channel with **no public username** and this bot is its owner or an
  administrator permitted to post. This verification is point-in-time only.
  Stored channel is **always DISABLED** for automated delivery; a verified
  destination alone never enables signal posting.
- Preview the last three PAPER signals **only inside the verified
  administrator's private chat** and inspect recent admin actions.

**Required boundaries:** both Telegram user ID and private chat ID must
match an explicitly preconfigured admin ID. No public/group-chat admin
actions. Callback IDs are bounded opaque SHA-256 identifiers, not raw source
paths; enable/disable operations enforce the current SQLite revision.
No Telegram file uploads, remote code installs or authorizations based on
chat-provided source; registering trusted Python requires independent
operator review and SHA256 pins via `naseri-custom register`.

## Mount into the same Telegram bot Application

For a **future, explicitly authorized nonproduction product startup**, where
an existing `python-telegram-bot==22.8` `Application` object already exists:

```python
from pathlib import Path
from naseri_markets.custom_admin_panel import CustomAdminPanel

panel = CustomAdminPanel(
    state_dir=Path("/path/to/private/custom-state"),
    admin_ids={YOUR_NUMERIC_TELEGRAM_ADMIN_ID},
)
panel.register(application)
# Mount AFTER existing bot admin handlers. Run only ONE bot polling/webhook
# process. Do NOT start a second poller with an active bot token.
```

For the isolated `multi-market-trading==0.4.0rc1` preview, opt-in to the
extra dependency `python -m pip install "multi-market-trading[telegram-admin]"`
when building/installing the separate staged wheel. The panel has no
automatic bootstrap and never downloads the bot token from GitHub.

**Current integration status:** the new product has no production Telegram
`Application` launcher yet, and the old v0.3.2 bot startup was NOT modified.
To display this UI in the *existing running* bot's admin keyboard requires
a separately authorized, tested integration/deployment plan because its
frozen `production_source/SHA256SUMS` cannot be silently changed. The
module and `register(application)` hook are ready for that integration,
but the buttons do NOT currently appear in a deployed bot. The `/custom`
command becomes available only after the hook is explicitly mounted.

## Signal delivery / PAPER vs FORWARD

**Explicit rule: setting a destination DOES NOT send a signal.** All
Custom-generated intents are PAPER-only by A7. The public delivery router
`decide_delivery` forbids PAPER publication to trading channels and
requires authenticated FORWARD market data, verified private-channel
access and separate publication enablement. Those prerequisites are not
present for the trusted local Custom worker. Hence A7 PAPER previews are
rendered only as private admin messages and the stored channel
`delivery_mode` is permanently `DISABLED` in this capability.

Activating real signals in a private channel requires separate future
authorization **and** an end-to-end authenticated market-data/runtime,
FORWARD permission, idempotent delivery and recovery tests; it is NOT
activated by this panel.

## Proprietary-engine boundary

NY First-Reversal remains **OWNER_ONLY**. Do not register, upload, compile,
encrypt, or repackage its private source into this public codebase or any
public install artifact. The panel cannot install arbitrary remote
code; it displays only locally registered public generic engines.

## CI verification

`tests/unit/test_custom_admin_panel.py` checks private-admin-only
authorization, correct callbacks and CAS revisions, audit-on-toggle,
selection of per-engine channels through mocked Telegram `getChat` /
`getChatMember` access, denial of public or non-admin channels,
route-changing races, private PAPER previews and the fact that no
`send_message` channel publication ever occurs. The CI workflow tests
this with the existing trusted local Custom E2E suite and checks
the separate clean staged wheel installs its optional Telegram admin
dependency. Full legacy regression, PostgreSQL and publication-safety
workflows must pass before merge.

**Verdict when CI is green:** `CUSTOM_ADMIN_PANEL_READY_TO_MOUNT_NONPRODUCTION`,
not `CUSTOM_ADMIN_PANEL_LIVE_DEPLOYED`.
