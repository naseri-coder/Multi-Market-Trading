# NASERI MARKETS A9 — Plugin lifecycle & settings integration

**Scope:** GitHub-only, offline PAPER management. A9 does NOT install or
execute third-party strategy packages, connect to a remote private engine,
provision a VPS, modify Telegram/BotFather, or access brokers.

## Implemented lifecycle

| Operation | Contract and safety |
|---|---|
| Register | Explicitly SHA-256-pinned ABI 1 **metadata**, disabled by default |
| Inspect/list | Transport-neutral settings cards for PUBLIC and PRIVATE engines |
| Enable/disable | PAPER-only dispatch permission, revision CAS; not live activation |
| Upgrade | Only while disabled; new approved SHA-256 and expected revision required |
| Unregister | Disabled-only, CAS-protected; removes metadata, **not strategy files** |
| Re-register | Persisted tombstone monotonic revision guards stale control sessions |
| Health | Honest **offline metadata** report; no fabricated process, feed, private entitlement or Telegram readiness |
| Audit | Local SQLite transactionally appended metadata lifecycle events; not tamper-proof |

`PluginManager` has added separate `a9_plugin_tombstones` and
`a9_plugin_audit` tables to the **offline plugin settings database**.
There is NO change to the historic production PostgreSQL schema or A3
Telegram outbox. Existing A8 plugin rows and revision contracts survive
the additive migration. Re-registering an uninstalled engine starts
disabled and uses a revision HIGHER than its tombstone.

A running A8 PAPER callback that sees a settings/installation incarnation
change may finish computing, but its result is discarded before being
persisted. It is **not** a process kill, security sandbox, or guarantee
against side effects inside a malicious or untrusted callback.

## Settings presentation adapter (future Telegram UI)

`naseri_markets.plugin_settings.PluginSettingsService` supplies
`inventory`, `inspect`, `register`, `set_paper_enabled`,
`upgrade`, `unregister`, `audit`, and `health_report` functions.
It requires an operator ID in an explicit allowlist for EVERY read/write.
A future Telegram integration **must independently verify the actor
from a trusted Bot API update** and enforce admin authorization before
calling this service. An ID or 'admin' flag copied from a client message
is not adequate authentication. No Telegram handler or connected Mini App
was deployed in A9.

The private plugin health state is always
`PRIVATE_OWNER_NOT_ATTESTED` until a separately authorized real
provider-identity, license, and authenticated remote-service protocol
is built. A descriptor hash proves local bytes only, NOT signature,
publisher authority or legal entitlement.

## Runnable local command interface

Operate only in a test checkout with a disposable directory that your OS
account controls. The CLI relies on local file permissions; the
`--allow-metadata-writes` flag is acknowledgement, **not authentication**.

```bash
python -m naseri_markets.plugin_admin --db /tmp/a9-demo.db inventory
python -m naseri_markets.plugin_admin --db /tmp/a9-demo.db health
python -m naseri_markets.plugin_admin --db /tmp/a9-demo.db \
  --allow-metadata-writes register examples/plugins/public-example.json \
  --sha256 <INDEPENDENTLY_VERIFIED_MANIFEST_SHA256>
python -m naseri_markets.plugin_admin --db /tmp/a9-demo.db \
  --allow-metadata-writes enable public_demo --revision 1
python -m naseri_markets.plugin_admin --db /tmp/a9-demo.db \
  --allow-metadata-writes disable public_demo --revision 2
python -m naseri_markets.plugin_admin --db /tmp/a9-demo.db \
  --allow-metadata-writes unregister public_demo --revision 3
```

Do not use an automatic hash generated from the same untrusted download
as proof of publisher authenticity. Commands never fetch code, run
private engines or activate network I/O.

## Frozen identities

The old `crypto-price-action 0.3.2` distribution, immutable
`production_source/SHA256SUMS`, `Dockerfile.production`,
`compose.yaml`, persistent PostgreSQL volume and the separate A6
`0.4.0rc1` distribution version remain unchanged.

## Test gate

A9 requires dedicated unit/E2E regressions including default-off,
unauthorized UI actors, stale revisions, changes in flight, remove while
active rejection, persistent tombstones and audits, isolated restart,
CLI command flow and pin/symlink negatives. Existing A5-A8, full
PostgreSQL, CodeQL, Docker and publication safety checks remain intact.

**Production/private plugin deployment is a separate stage:** process
sandbox, owner-controlled private engine endpoint, mutually
authenticated transport, entitlement checks, rollback, operator-approved
BotFather/admin installation and live E2E are not supplied by A9.
