> Historical reference only; not current release proof.
> Original source: `integration_phase1/docs/database_mapping.md`; SHA256: `7b862bf0041ba9bed1d78bc32a559ffacabd3a2f6875ae89d3186ddef62792e4`.

# Integration Phase 1 — Brooks → Existing Signal Domain / PostgreSQL Mapping

## Existing domain preserved

The existing project remains the authoritative lifecycle domain:

- `signals`
- `signal_targets`
- `signal_events`
- `SignalService`

Brooks Core becomes a producer. It does **not** create a parallel signal lifecycle.

## Field mapping

| Brooks integration field | Existing destination | Notes |
|---|---|---|
| symbol | signals.symbol | Existing normalization/validation stays authoritative |
| direction | signals.direction | LONG / SHORT only |
| entry_price | signals.entry_price | Existing Decimal validation |
| stop_loss | signals.stop_loss | Existing geometry validation |
| leverage | signals.leverage | **Must be supplied by integration/runtime config; Brooks Core does not currently produce leverage** |
| description | signals.description | Optional human-facing summary |
| targets[] | signal_targets | Added through existing `SignalService.add_target()` |
| source_signal_id | signal_automation_metadata.source_signal_id | Producer identity |
| generation_mode | signal_automation_metadata.generation_mode | SHADOW / PAPER / LIVE |
| publication_scope | signals.publication_scope | INTERNAL / PRIVATE_TEST / PUBLIC / VIP / PUBLIC_VIP |
| market_snapshot_id | signal_automation_metadata | Required |
| market_snapshot_hash | signal_automation_metadata | Required |
| engine_version | signal_automation_metadata | Required |
| rule_set_version | signal_automation_metadata | Required |
| configuration_version | signal_automation_metadata | Required integration/deployment config version |
| setup_type | signal_automation_metadata | Nullable |
| reasoning[] | signal_automation_metadata.reasoning | JSONB array |
| rule_ids[] | signal_automation_metadata.rule_ids | JSONB array |
| failed_rules[] | signal_automation_metadata.failed_rules | JSONB array |
| rule evaluations | signal_rule_evidence | Ordered immutable evidence rows |

## Idempotency

A deterministic idempotency key is SHA-256 over:

`BROOKS | generation_mode | SYMBOL | timeframe | market_snapshot_hash | direction | setup_type | engine_version | rule_set_version | configuration_version`

Database uniqueness on `(producer, idempotency_key)` is the final race-condition guard.

The integration transaction must be:

1. begin transaction
2. check/attempt idempotency
3. create signal through existing `SignalService`
4. add all targets through existing `SignalService`
5. insert `signal_automation_metadata`
6. insert ordered `signal_rule_evidence`
7. commit

If the uniqueness constraint fails, the whole transaction must roll back. Do not create a second signal.

## Publication scope problem discovered by audit

Existing public signal queries primarily use signal lifecycle status. A PAPER signal must be `OPEN`
if the existing target/stop lifecycle is reused, but an OPEN PAPER signal must **not** leak into
public user lists.

Therefore `publication_scope` is added to `signals` with default `PUBLIC` to preserve all existing rows.

Required later integration change:
- public user queries: include only `PUBLIC` / `PUBLIC_VIP`
- VIP queries: include only `VIP` / `PUBLIC_VIP`
- private test publication: `PRIVATE_TEST`
- shadow storage: `INTERNAL`

Until those query filters are implemented and tested, PAPER/LIVE automation must not be enabled.

## Win-rate isolation problem discovered by audit

Current win-rate aggregation counts latest TARGET_HIT / STOP_HIT events without generation-mode filtering.
If SHADOW or PAPER events are stored in the same lifecycle, they would contaminate production win rate.

The metadata table therefore includes `counts_toward_performance`.

Required later analytics change:
- join `signal_automation_metadata`
- manual signals: preserve current policy explicitly
- automated signals: count only rows where `counts_toward_performance = true`
- SHADOW/PAPER must always be false
- LIVE may be true only after explicit production approval

## Configuration version gap

Brooks Core phase contracts version engine/rules, but the current `SignalDecision` object does not carry
`configuration_version`. Integration requires it as an explicit deployment/runtime input so that
engineering thresholds are reproducible and audit-safe.

No placeholder like `UNVERSIONED` should be used in production.

## Existing lifecycle reuse

Automated outcomes should call existing methods rather than write events directly:

- `SignalService.hit_target(...)`
- `SignalService.update_stop_loss(...)`
- `SignalService.close_signal(...)`
- stop-hit lifecycle path where available in the existing service

This preserves event ordering and win-rate compatibility.
