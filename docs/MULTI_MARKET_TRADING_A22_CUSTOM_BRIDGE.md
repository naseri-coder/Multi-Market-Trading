# Multi Market Trading — A22 Custom Runtime Bridge & Permission Isolation

**Status: NON-PRODUCTION / PUBLIC GENERIC CUSTOM DATA ONLY**

## A21 owner boundary stays binding

**NY First-Reversal is OWNER_ONLY.** The public repository must never
publish, install, decode, decrypt, bundle, market or execute the proprietary
strategy — even an encrypted, obfuscated or commercially labelled copy.
The A22 bridge rejects `owner_only`, `commercial_candidate`,
`ny_first_reversal` and reserved NYFR aliases. Only independently
registered A21 `public_custom`/`generic_custom` metadata is eligible.

This stage builds a generic bridge for **precomputed third-party PAPER
envelopes**, not an installer or an engine/plugin code loader. It receives
only operator-provided exact UTF-8 A7 envelope **bytes** for a quote;
there is no arbitrary callback argument, network endpoint, executable
artifact, public private-engine marketplace or live feed.

## A22 architecture

`CustomPaperRuntimeBridge` uses the established A7
`ExternalPaperEngine`, A2 `EngineRegistry`/`MultiEngineRunner`,
and A7 `PaperJournal` without altering the existing A8 engine
policy. A8 continues to require public **in-process** adapters and
private **external** mock adapters. The new A22 bridge instead runs
the generic public custom **data** path separately. No new A8 public
external executable loophole is introduced.

1. The operator registers the exact A21 Custom descriptor in the
   in-memory catalog with an independently approved SHA-256 byte pin.
   Hash equality is **not** proof of publisher identity or trust.
2. The operator attaches its exact registered public `generic_custom`
   descriptor, explicit bounded instrument allowlist and a **verified**
   market session. The engine is **disabled by default**.
3. The platform must be constructed with explicit `paper_enabled=True`.
   An operator must individually enable each engine via exact descriptor
   digest and CAS revision; neither attaching nor catalog listing
   authorizes a dispatch.
4. The operator supplies bounded A7 PAPER bytes, quote, and exact engine
   revisions for a dispatch. Before invoking the data-only fixed
   provider, A22 checks every engine permission, identity, market,
   revision, replay/synthetic source, A7 envelope and engine session.
5. A single `MultiEngineRunner.process` dispatches one tick to all
   approved Custom engines. Signals undergo A7 envelope geometry and
   exact A2 registry validation. The only durable side effect is a
   local, A7 **PAPER-only** journal transaction. There is no broker or
   Telegram path.
6. If any engine is disabled during an async dispatch, revisions change,
   or the platform switch is removed, A22 **discards the entire result
   before persistence**. Revocation is always allowed without a hash or
   token. Invalid packets fail closed **before** the quote runner and
   journal, so a bad Custom packet cannot commit partial batches.
7. An engine whose slot is faulted must not be silently restarted or
   reset by a toggle; a separately authorized explicit rebuild is
   required. There is no auto-restart or automatic trust promotion.

### Permission separation

- One A21 pinned descriptor per public Custom engine; immutable
  identity on registration and binding; no impersonation by marketing label
- Per-engine `enabled=False` default, individual CAS revisions, paper
  platform-wide explicit opt-in and unconditional disable
- Only `paper_analysis`, `replay_or_synthetic`, precomputed A7
  `evidence_mode=paper`
- No cross-market, cross-symbol, cross-engine, future/causally invalid
  timestamps, broker access, network transport or raw payload injection
- One bounded batch (1–16 engines), packet per engine ≤ 8192 bytes
- Prepared data-only adapter does not execute Custom source code or
  import dynamically from plugin directories
- No strategy source, binary, ciphertext or NYFR artifact in public build

### Limits — do not overclaim

**This is an in-process DATA bridge, not an OS sandbox for unknown
third-party Python, binaries, containers or strategy scripts.** The only
callback is the built-in `_FixedEnvelopeSlot`, and real third-party
code is NEVER passed to it. A21 digest pin is not a cryptographic
publisher signature or a commercial license. CAS is local cooperative
operator state, not secure against host compromise. The quote quality
gate and journal remain development PAPER components. A20's stricter
guardian/cgroup rehearsal is not automatically linked to an arbitrary
third-party source/runtime here.

An actual Custom executable hosting layer, signed independent publisher
verification, tenant privileges, deployment and UI toggles are future
distinctly authorized stages. OWNER-ONLY NYFR commercialization remains
a separate private project decision; no public installation route
should ever be used for its implementation.

## CI verification

A22 dedicated GitHub workflow runs A7/A8/A12–A22 regression tests,
strict Ruff lint, old frozen source hash preflight, AST inspection,
A6 public-only distribution preview and no-executable-artifact checks.
Standard PR full corpus on disposable PostgreSQL and Publication Safety
must both succeed before merge.

**Expected verdict after all CI PASS: A22_GENERIC_CUSTOM_PAPER_BRIDGE_VERIFIED.**
