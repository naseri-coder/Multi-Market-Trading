# A10 — Private Engine Authenticated Connector (offline, non-production)

**Status:** Github-only implementation and security test harness. No live
transport, VPS, broker, Telegram, BotFather, key provisioning, private
repository mutation, real NYFR engine evaluation or production cutover.

## Security architecture

```text
PUBLIC Multi-Market-Trading (offline PAPER only)
   PluginManager enabled/private + pinned metadata + incarnation fence
      |
   PrivatePaperConnector (per-request random 128-bit challenge)
      | HMAC-SHA256 / client->owner directional key [offline bytes]
      v
   injected abstract async Exchange callback (CI fixture only)
      |
   Owner's separate private strategy service (NOT IMPLEMENTED)
      |
      | HMAC-SHA256 / owner->bot independent key
      v
   timestamp, TTL, engine+version, challenge, MAC validation
      -> SQLite durable nonce anti-replay + explicit key-id revocation
      -> exact A7 PAPER envelope (quote identity, timestamp, geometry)
      -> existing typed ExternalPaperEngine -> A8 PAPER journal
```

The GitHub CI exercises a **fake owner** with two fixture-only keys, not
an actual remote TLS server. HMAC establishes possession of symmetric
keying material; it cannot prove legal licensing, software authorship,
publisher origin, trusted hardware custody, or confidentiality in
transit. A real connector MUST use audited end-to-end encrypted
transport (mTLS recommended), pinned owner identity with independent
trust-store/provisioning, rotation and dual-control revocation before
any production deployment. Exposing HMAC shared secrets to untrusted
bot hosts forfeits impersonation resistance; for strong protection
keep strategy execution and secrets under the owner's control and use
distinct appropriately scoped credentials.

## Data contract and controls

- Strict `version=1` packet schema, exact IDs and distinct directional
  keys (at least 32 random bytes each, injected by an operator).
- HMAC-SHA256 domain-separated canonical signing, constant-time tag
  comparison; only the explicitly expected key ID and direction accepted.
- Each request has an OS-entropy 128-bit nonce and short lifetime
  (max TTL 30 seconds), bounded future skew (5 seconds).
- Each response MUST reference the specific request's nonce, which stops
  valid-but-unrelated response substitution. Response message nonce is
  consumed in a dedicated SQLite ledger that persists across restarts.
- Local `ReplayFence.revoke(key_id)` immediately and durably rejects the
  key in this installation; failed replies are not accepted.
- All signals must pass A7's strict synthetic/replay PAPER parsing before
  this facade returns them. No live quote, trade or publication path.
- Private plugin must be installed as **pinned metadata**, explicitly
  PAPER-enabled, exact engine/version/digest and unchanged installation
  generation in the A9 settings database. Disable/remove/reinstall is
  fail-closed and requires a fresh connector instance.
- `asyncio.wait_for` bounds an injected async callback's wait time,
  but DOES NOT kill arbitrary process code or provide sandboxing.
- `ConnectorStatus` accurately reports **real owner authenticated=False**,
  **network connected=False**, **license verified=False**.

## Example integration (pseudocode, offline only)

```python
from naseri_markets.external_abi import ExternalPaperEngine
from naseri_markets.private_connector import ConnectorKeys, PrivatePaperConnector
from naseri_markets.private_protocol import ReplayFence

# manager is an A9 PluginManager already containing an independently pinned,
# explicitly PAPER-enabled PRIVATE engine descriptor.
# exchange is an explicitly injected authenticated test callback; not a URL.
connector = PrivatePaperConnector(
    manager=manager,
    fence=ReplayFence("/path/outside/source/to/replay.db"),
    engine_id="private_example",
    engine_version="1.0.0",
    approved_digest=APPROVED_DESCRIPTOR_SHA256,
    keys=ConnectorKeys(
        "client_k1", SECURE_CLIENT_KEY_FROM_TRUSTED_CUSTODY,
        "owner_k1", SECURE_OWNER_KEY_FROM_TRUSTED_CUSTODY,
    ),
    exchange=approved_offline_exchange,
)
adapter = ExternalPaperEngine("private_example", "1.0.0", connector)
# Register adapter with the A8 ManagedPaperPlatform and A2 EngineBinding.
```

Do not copy keys into a repository, log, Dockerfile, manifest, CLI
argument, Telegram chat or tests. Fixture-only keys are intentionally
non-secret and must never be used outside the GitHub test environment.

## Unimplemented production prerequisites

A10 is an **authenticated offline protocol prototype**, NOT a secure
production private engine deployment. Subsequent independently authorized
work is required for signed publisher and entitlement verification,
provider-controlled isolated execution, authenticated TLS network transport,
rate limits, service discovery, key custody and expiry/rotation/recovery
ceremonies, process sandboxing and live feed attestation.

Existing `crypto-price-action 0.3.2`, `production_source/SHA256SUMS`,
Compose volumes, Docker release, `multi-market-trading 0.4.0rc1`,
A3 Telegram delivery outbox and NYFR PRIVATE repository remain unchanged.
