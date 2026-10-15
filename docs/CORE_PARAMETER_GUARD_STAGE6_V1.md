# Stage 6 — Reviewed Core Parameter Guard V1

**Scope: NONPRODUCTION · DATA-ONLY · REVIEWED SCHEMA PIN · NO LIVE/SIGNAL EXECUTION**

## Architecture and why it is separate

The existing Multi-Market-Trading `CoreManifest` already defines stable core IDs/versions, setups, ABI, markets and supported events. The Stage-12 Trading Control Center already enforces owner/account settings, approved bindings, PAPER request flags and capital-preview rules. Neither layer currently defines a cross-strategy, parameter-by-parameter contract for numerical strategy configuration. The new `naseri_markets/core_parameter_guard_v1.py` is an **additive, independent, pure validation component**, not a new control plane or trading runtime.

There is **no automatic wiring to Stage-12, Stage-7 strategy evaluation or Production**. This stage creates a reusable guard for future separately authorized per-core settings support. The existing settings and their database remain unchanged. No strategy Python code is imported, parsed, evaluated or executed.

## Exact schema and settings

A trusted host must retrieve a separately reviewed parameter schema, bind it to a real approved core identity/version, and **pin its exact SHA-256 digest outside the untrusted settings input**. A checksum supplied by the same untrusted user as the schema itself is only a checksum, *not trust or authorization*. The validator uses that explicit pin and refuses drift or an altered core identity/version.

Example schema (no execution authority):

```json
{
  "schema_version": 1,
  "core_id": "example_core",
  "core_version": "1.0.0",
  "parameters": [
    {"name": "fast_period", "kind": "integer", "min": 2, "max": 100, "step": 1},
    {"name": "slow_period", "kind": "integer", "min": 3, "max": 200, "step": 1},
    {"name": "stop_buffer", "kind": "decimal", "min": "0.10", "max": "1.00", "step": "0.05"},
    {"name": "max_buffer", "kind": "decimal", "min": "0.20", "max": "2.00", "step": "0.05"},
    {"name": "use_confirmation", "kind": "boolean"},
    {"name": "average_type", "kind": "choice", "options": ["ema", "sma"]}
  ],
  "relations": [
    {"left": "fast_period", "op": "lt", "right": "slow_period"},
    {"left": "stop_buffer", "op": "lt", "right": "max_buffer"}
  ]
}
```

Matching settings are exactly:

```json
{
  "schema_version": 1,
  "core_id": "example_core",
  "core_version": "1.0.0",
  "values": {
    "fast_period": 10,
    "slow_period": 30,
    "stop_buffer": "0.25",
    "max_buffer": "0.80",
    "use_confirmation": true,
    "average_type": "sma"
  }
}
```

The host obtains `trusted_schema_sha256` from its separately approved manifest/publisher review. Example usage with a host-approved pin:

```python
from naseri_markets.core_parameter_guard_v1 import validate_core_parameters

result = validate_core_parameters(
    reviewed_schema_bytes,
    submitted_settings_bytes,
    expected_core_id="example_core",
    expected_core_version="1.0.0",
    trusted_schema_sha256=host_approved_schema_sha256,
)
assert result.verdict == "VALIDATED_OFFLINE_PARAMETER_VALUES_ONLY"
assert result.activation_authorized is False
```

## Fail-closed validation contract

- Schema bytes (maximum 48 KB) and settings bytes (maximum 8 KB) must be strict JSON objects; duplicate keys, unknown fields, JSON floats, NaN/Infinity and type coercion are refused. All declared parameters must be supplied; no silent defaults, unknown/extra values or partial updates.
- A core identity/version mismatch or changed reviewed schema SHA-256 is refused before parameter evaluation.
- Parameter types: `integer` (exact JSON integer, not bool; bounded min/max/step), `decimal` (bounded finite decimal **string**, never binary float; exact min-origin step grid), `boolean` (JSON true/false only) and `choice` (closed, alphabetically sorted finite option inventory). At most 32 parameters.
- Cross-field numerical constraints: static `lt`, `lte`, `gt`, `gte`, `eq` and `neq` between declared numeric fields; at most 48 relations. The guard checks each relation against exact values without Python `eval`, `exec`, arbitrary AST execution, scripts or dynamic imports.
- Privileged operational setting names are reserved, including API keys, LIVE flags, broker order flags, publication toggles, leverage and account budget. This naming fence is defense-in-depth **only**: a caller must still separately enforce risk, strategy ownership, authentication and production authorization.
- Refusals expose stable codes, not raw parameter values or submitted secrets. Successful outputs return core/version identities, bounded counts, input SHA-256 fingerprints and inert flags; no raw settings, trading permissions, order decisions or customer data.
- The caller is responsible for **atomic persistence**, host authentication, actual CoreManifest match, schema pin custody, compare-and-swap revision, and any eventual Stage-12 UI integration. Validation is not permission to run or publish a trading signal.

## Tests and release restrictions

```bash
python -m pytest -q tests/unit/test_core_parameter_guard_v1.py
```

Test vectors cover pin forgery, cross-core/version mismatches, incorrect fast/slow periods, exact decimal step-grid arithmetic, malformed numeric values, unknown/missing parameters, duplicated JSON fields/schema entries/relations, invalid operators, executable-expression attempts, choice violations, privileged names, bounds, secrecy of thrown errors and immutable inert success receipts.

Only **three new files** are authorized in this stage: the validator, isolated unit tests and this documentation. No edits to the legacy production runtime, strategy implementations, core manifests, Stage-12 store or Telegram handlers, private engines, databases/migrations, settings persistence, releases or deployment. This does **not** expose parameter editing in the user-facing panel yet; such integration needs a subsequent separately approved stage with revisioned ownership controls and independently trusted per-core schema pins.

No upstream project's branding, identifiers or code have been copied. The module is independently implemented against the public project's own contracts and security boundaries. Successful CI tests attest implementation behavior on synthetic cases, not live safety, strategy profitability or production readiness.

**Stop after Stage 6.** Protected GitHub CI must pass on the final PR commit before merge.
