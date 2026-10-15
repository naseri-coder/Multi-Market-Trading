# Stage 7 — Offline Research MCP Connector V1

**STATUS: NONPRODUCTION / INERT / STDIO-ONLY · NO DEPLOYMENT OR LIVE TOOL ACCESS**

## Purpose and protocol scope

This stage provides a small, purpose-built [Model Context Protocol](https://modelcontextprotocol.io/) stdio server for AI coding/research clients to call existing **offline** diagnostic functions. It reuses NASERI MARKETS research contracts instead of creating a second exchange adapter, new research engine, new panel, or command executor.

The server is strictly **opt-in**, with only an explicit local CLI entry point and no auto-start, no network listener, no HTTP/SSE, no Telegram bot mounting, no broker calls and no database mounting. It requires:

```bash
PYTHONPATH=. python -m scripts.mmt_offline_mcp_v1 --ack-offline-research
```

Run from the public repository in an isolated development environment, using **Python 3.12** and fixture-only inputs. Client configuration example for an MCP app **that supports local stdio commands**:

```json
{
  "mcpServers": {
    "naseri-markets-research": {
      "command": "python",
      "args": [
        "-m",
        "scripts.mmt_offline_mcp_v1",
        "--ack-offline-research"
      ]
    }
  }
}
```

The working directory must be the local public repo root (or the package must be installed and the runnable wrapper made available). **This is a configuration example**, not proof that a particular client has been connected or a server started. Do not paste API tokens or private research into client configuration. Installation and external client connection require a separate user action.

Two MCP protocol revisions are implemented **locally over newline-delimited JSON-RPC stdio**:

- **Modern `2026-07-28`**: `server/discover`, per-request `_meta` protocol version/client capabilities, `tools/list` and `tools/call` responses with `resultType=complete`. No legacy handshake. Any unsupported version fails with a fixed, explicit `-32022` response.
- **Legacy `2025-11-25`**: `initialize`, explicit `notifications/initialized` followed by `tools/list` and `tools/call`. No silent fallback if version negotiation fails, no cross-era switching after initialization.
- Also responds to `ping`, ignores unsolicited notifications, and rejects unsupported RPC methods. No `resources`, `prompts`, `sampling`, `subscriptions`, roots, elicitation, HTTP transport or background tasks are provided.

This is a **narrow interoperability implementation**, not a full MCP SDK or externally certified compatibility with every MCP client. Its protocol framing is intentionally limited to stdio with one bounded JSON object per line; the optional official SDK may be evaluated separately if required later. The implementation does not add any new dependencies to public lockfiles or release manifests.

## Four tightly scoped read-only tools

| MCP tool | Capability | What it cannot do |
| --- | --- | --- |
| `research_capabilities` | Return static capability and safety-limit flags | Enumerate local code, accounts or secrets |
| `diagnose_exchange_failure` | Classify bounded manually supplied error evidence via existing Stage-1 diagnostics | Read live errors, show raw secrets, retry/cancel orders |
| `normalize_order_status` | Normalize Stage-2 provider status labels with explicit unknown result | Assume fills, post accounting or initiate orders |
| `audit_overfit_fixture` | Invoke the existing Stage-5 PBO/DSR analysis for an **operator-supplied** complete, bounded, pre-holdout matrix | Read files/paths, access live data, optimize parameters or publish signals |

No credential-bearing inputs, arbitrary file paths, user-owned filesystem traversal, subprocess execution, GitHub write privileges, request routers, SQL tools or dynamic tool discovery exist. The success result of **every** tool explicitly refuses trade authorization. Tool annotations are advisory; the real barrier is the narrow hardcoded implementation and absence of write/deploy APIs.

### Complexity and input fences

- Every stdio JSON-RPC line is limited to 100 KB. Oversized lines are drained using bounded reads and refused; processing continues for later frames. No unsanitized request or exception is echoed to stdout/stderr.
- Only known RPC methods and the four allowlisted tools can be called. Tool arguments require an exact schema: unknown keys, unknown venue values, invalid types and oversized strings are refused.
- The PBO/DSR matrix input is text supplied **in the call**, capped at **80 KB, 128 time periods, 8 candidates and 4 or 6 CSCV blocks**. The existing Stage-5 module independently enforces a complete, evenly sampled pre-holdout trial inventory, strict UTC/decimal rules and mathematical validity. The MCP tool never opens local matrix paths or retrieves datasets.
- The MCP process holds no credentials and has no network or filesystem **functions in its exposed tool surface**. It does not constitute an OS-level sandbox; an untrusted client or model should run it in an isolated developer environment with no production files or network privileges.
- No source code from other products is copied. Names, identifiers and public docstrings belong exclusively to this project.

## Security and validation

- **Transport**: only stdin/stdout, explicit `--ack-offline-research`. The launcher is not embedded in the production bot and emits only JSON-RPC lines on stdout.
- **Protocol**: legacy/modern initialization and discovery, per-request version checking, deterministic tool listing, correct `resultType`, unknown-method rejection, invalid ID/JSON refusal, idempotent notifications.
- **Data**: hidden API-key markers never echoed, ambiguous network errors require reconciliation, native unknown order statuses never inferred to be safe, oversized/hostile matrices are rejected.
- **Execution**: no broker orders, Telegram publication, runtime core toggling, plugin loading, file reads, local repo scan, database connections, shell, git writes or server deployment.
- **Research integrity**: outputs remain `DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF`; PBO/DSR claims are subject to the original Stage-5 source-data and complete-trial-history limitations.

### Reproducible local acceptance

```bash
python -m pytest -q tests/unit/test_offline_research_mcp_v1.py
```

The PR must also pass the repo's full GitHub Actions safety, PostgreSQL, general regression and public release checks on its **final head** before merge. No stage-8 roadmap work is authorized by this PR.

## Files and unchanged components

Stage 7 adds exactly four files: `naseri_markets/offline_research_mcp_v1.py`, `scripts/mmt_offline_mcp_v1.py`, `tests/unit/test_offline_research_mcp_v1.py`, and this document.

No existing source, manifests, lockfiles, application startup, database/migration, exchange adapter, strategies, private cores, production runtime, Telegram credentials, or release/deployment settings are modified. Future installation packaging, complete MCP SDK compatibility, trust/sandbox hardening and actual client connection remain separately approved work.
