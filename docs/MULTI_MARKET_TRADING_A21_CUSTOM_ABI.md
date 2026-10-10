# Multi Market Trading — A21 Custom Engine ABI / Owner-Exclusive Strategy Boundary

**STATUS: NON-PRODUCTION / CONTRACT-ONLY / NO PRIVATE ENGINE DEPLOYMENT**

## Binding owner decision — NY First-Reversal

The developer-owner **does not authorize NY First-Reversal for public
installation or distribution under any packaging style**. This includes:
plaintext source, precompiled binaries, encrypted archives, obfuscated
plugins, licensed public download packages and any universal public
plugin installer. **Encryption does not make it redistributable.**

- NY First-Reversal and its proprietary algorithms remain **outside**
  the public repository, public build contexts, public engine registry
  listings and future public extension marketplace.
- Current access decision: **OWNER_ONLY**. Possible eventual
  monetization/licensing is **not authorized yet**, and needs a
  separately approved private distribution architecture; the public
  app must never become a backdoor delivery vehicle for this strategy.
- A metadata-only, owner-local declaration is possible for contract
  research. Declaring is NOT publishing, shipping, installing,
  decrypting, executing or licensing.
- Renaming a package, shipping only ciphertext or providing an
  access token does not change this decision. Fail closed.

## Custom engine extension contract (future-compatible public framework)

The public framework will accept **independent third-party CUSTOM
engines** through a documented ABI while keeping provenance and
distribution separate from access and execution:

| Category | Discovery in public catalog | Executable delivery | Current authority |
| --- | --- | --- | --- |
| `public_custom` | Public metadata only | NONE | ABI compatibility checks only |
| `owner_only` | Never published | NONE | Owner-only metadata, no run |
| `commercial_candidate` | Never published | NONE | Design placeholder, no license |
| `ny_first_reversal` strategy family | Owner-local ONLY | NEVER through public app | Owner-only by explicit decision |

All categories in **A21** remain `CONTRACT_ONLY_NOT_INSTALLED`.

The v1 contract in `naseri_markets/a21_custom_contract.py` is
small, UTF-8 JSON and independently SHA-256-pinned. This is
**metadata integrity only**, not publisher authentication. It requires
the *exact* fields:

```json
{
  "schema_version": 1,
  "engine_id": "custom_demo",
  "engine_version": "1.2.3",
  "publisher": "community.example",
  "markets": ["crypto", "index"],
  "access_policy": "public_custom",
  "strategy_family": "generic_custom",
  "adapter": "external_contract",
  "abi_version": 1,
  "distribution": "metadata_only",
  "artifact_policy": "no_executable_or_ciphertext",
  "permissions": ["paper_analysis"],
  "runtime_mode": "replay_or_synthetic",
  "execution_authorized": false
}
```

The catalog allows independent Custom contracts from multiple
publishers, versioned identities, and crypto/forex/index/metal market
lists. It rejects duplicated JSON keys, malformed/future versions,
missing pins, unknown fields, URL/process entrypoint injection,
binary/ciphertext embedding, licensing bypass, live permissions and
all arbitrary install hooks. Registration is idempotent only for
identical immutable metadata; ID collisions fail closed.

`CustomContractCatalog.public_listings()` exports **only** sanitized
`public_custom` metadata. Owner inventory is a distinct
operator-only method and is NOT a public endpoint. Protected strategy
aliases are blocked from public or commercial-candidate policies.

`inspect_custom_paper_fixture()` checks an **already injected**
external PAPER proposal against the existing A7 data envelope and
an A21 contract identity/market. It never loads a provider, subscribes
to live quotes, sends orders, writes a DB or attaches an engine.

## Explicit A8/A21 compatibility boundary

Existing A8 accepts in-process PUBLIC engines and mock
external-contract PRIVATE engines. A21 **does not silently change
this wiring**. A new publicly listed Custom contract with
`adapter=external_contract` is only an accepted metadata
description: its actual executable/transport binding is NOT READY.
A future separately authorized stage may build an audited public
extension adapter, without ever making the protected core available.

Existing A12 owner admission, A15 publisher signature, A18 Guardian
and A20 scoped fixture keep their current, **non-production**
behaviors. The A21 parser does **not** grant or inherit these
capabilities automatically. No actual licensed engine is executed.

## Permanent future design decision

**The owner/private NY First-Reversal component must remain isolated.**
Separate future owner-approved work may consider a private commercial
licensing system or owner-exclusive execution service, with server-side
key custody, genuine signed releases, tenant entitlements, off-host
anti-rollback evidence, revocation and audits. If the owner chooses
not to commercialize, `owner_only` remains the permanent boundary.
Either way, **no public installable NYFR artifact** — encrypted
or otherwise — is permitted.

The public framework should eventually offer a **generic custom
engine interface** (not a copy of this private engine): a signed
publisher contract, independent permissions, strict sandbox,
paper-first evaluation, external service ABI, version negotiation,
owner/vendor configuration, toggles and revocation. Design and
executable deployment are separate approvals.

## A21 verification and limits

- Unit tests: generic public contract registration, future private
  candidate isolation, owner-only NYFR, aliases, metadata-only public
  catalogs, malicious/custom plugin metadata, encrypted package
  attempts, A7 paper envelope, A8 incompatibility detected without
  bypass, A6 public preview contains no private module or encrypted
  artifact.
- CI checks historical manifest, A7/A8 regressions, A12–A20
  non-production boundaries, source static inspection and A6 public
  preview; whole repository regression and publication safety run
  as independent merge gates.
- No code scanner can reliably recognize **arbitrarily renamed or
  perfectly encrypted** proprietary logic. The protection is a
  distribution/authorization policy: A21 has no executable
  delivery format at all, and the public build copies only
  approved public-source modules. Human release review and an
  eventually audited allowlist are still required to prevent
  accidental leaks in future unrelated code changes.

**Verdict on successful CI: A21_CUSTOM_CONTRACT_ONLY_OWNER_NYFR_PROTECTED.**
