# A8 Universal Plugin Framework — public core, public/private engines

**Status:** GitHub-only, non-production implementation. All configuration
and E2E execution below is strictly **offline PAPER/replay**. No VPS,
BotFather, Telegram messages, MT5 broker orders, actual private NYFR
source, credentials, live feed or runtime deployment.

## One generic contract, two distribution choices

The main `Multi-Market-Trading` project stays public. Every engine has the
same metadata ABI 1 (`naseri_markets.plugin_descriptor`), engine ID/version,
supported markets and **only** `paper_analysis` permission:

| Engine visibility | Adapter | Code ownership |
|---|---|---|
| `public` | `in_process` | Open source, operator-supplied trusted callback |
| `private` | `external_contract` | Strategy code remains owner-controlled outside public repo |

The private adapter uses the A7 data-only paper envelope contract; its public
stub contains no NYFR logic. **A8 does not start a remote private service,
authenticate its publisher, or download or dynamically import an engine.**
Running externally under the owner's control will require a separately
specified process/network trust architecture.

## Lifecycle and setting toggles

1. Obtain an independently approved manifest SHA-256 from a trusted operator
   channel. A checksum pin proves byte identity, NOT a publisher signature.
2. `PluginManager.register(raw, approved_sha256=pin)` registers only
   descriptor metadata in an explicitly supplied on-disk SQLite file.
   Registered engine defaults to **disabled** across restarts.
3. UI/settings may call `list()` / `get(id)` and
   `set_enabled(id, enabled=True/False, expected_revision=...)`.
   Stale UI revisions fail closed, preventing lost updates.
4. An engine version upgrade requires `replace(..., expected_revision)`,
   performed while that engine is disabled. The new manifest must again be
   explicitly pinned.
5. An approved caller injects an adapter into `ManagedPaperPlatform.attach`,
   using an A2 typed `EngineBinding` and A7 external envelope when private.
   This code must come from a separately trusted source. It is NOT a sandbox.
6. `ManagedPaperPlatform.process` reads enabled settings on EACH replay tick,
   passes an allowlist to the underlying runner BEFORE calling any engine,
   validates typed PAPER output, and persists only into the A7 paper journal.
   A setting/version change during async evaluation drops the entire pending
   batch; an already-running callback cannot be unexecuted or force-killed.

The settings store and PAPER journal have distinct SQLite files. Neither is
the production signal outbox, PostgreSQL schema, or trading database.

## Plugin author template

- Public demo manifest: `examples/plugins/public-example.json`
- Private *metadata-only* descriptor: `examples/plugins/private-example.json`
- Empty public callback scaffold: `examples/plugins/public_template.py`

Manifests allow **no executable path, URL, shell command, token, strategy
formula, or arbitrary permissions**. Both kinds use one abstract
`EngineDescriptor` and compatible SignalIntent. Plugin registration is
metadata preparation, *not* software installation.

## Invariants and scope boundary

- Package `multi-market-trading==0.4.0rc1` and historical release 0.3.2
  remain unchanged; existing Docker/Compose, manifests and SQL untouched.
- No runtime engine is enabled by default; private code cannot be obtained
  from this repository.
- No live market connection, Telegram delivery or trades; tests use only
  deterministic fixtures.
- The simulation of private external envelopes does NOT authenticate an
  engine identity, entitlement or quote feed; future production requires
  signed provenance/entitlements and isolated remote execution.
- No UI screen is deployed: the settings backend is now usable by a future
  Telegram settings interface after separate authorization.

**A8 passes only after its dedicated tests and all existing GitHub CI
security, PostgreSQL, Docker and publication controls pass.**
