# A6 / 0.4.0rc1 — isolated NASERI MARKETS public package preview

**Gate:** Source & Docker candidate only. Do NOT tag, deploy, enable Telegram,
open an order, connect to live price feeds, or claim v0.4 production readiness.

## Real changes
- A second, independently versioned Python wheel (`multi-market-trading`,
  `0.4.0rc1`) is built from the public `naseri_markets` modules, without
  repackaging any legacy `production_source/app` or private NYFR source.
- Its CLI (`naseri-markets --check`) reports a JSON `OFFLINE_PREVIEW`
  status. `--engine-plan` accepts an A5 metadata-only disabled-engine plan.
- `Dockerfile.platform` produces an independent, rootless image; the
  `compose.platform.yaml` **validation-profile only** service has no
  network, host ports, secrets, database service or volume. It terminates
  after its offline check.
- `scripts/a6_prepare_package.py` stages exact allowed public modules
  in a NEW out-of-tree directory and outputs their SHA-256 digests.

## What this does NOT do
This preview does not connect the existing Brooks/FM legacy services to the
new `MultiEngineRunner`. A5's disabled-only engine manifest is not a
plugin installer; private NYFR strategy is not installed and its source
cannot be imported. The new image does not operate a Telegram bot.
A standalone database migration is NOT implemented or performed.

The historic Python package `crypto-price-action==0.3.2`, its immutable
manifest, `Dockerfile.production`, `compose.yaml`, and the persistent
volume `crypto-price-action_postgres_data` remain untouched. The two
versions MUST NOT share or rename database volumes without a future
audited migration.

## Before a production-ready multi-market release
1. Freeze a versioned signed/provenance-checked private plugin ABI
   and explicitly approved, isolated Brooks/FM adapters, without
   exporting any NYFR proprietary rules into PUBLIC Git history.
2. Map and test schema ownership, forward migrations, backup/restore,
   data retention and downgrade fences with a **full legacy schema**
   rehearsal and at least two independent disposable PostgreSQL volumes.
3. Add authenticated live market providers, independent read-only
   feed attestations, verified channel entitlements and an operator-approved
   safe startup/stop workflow; never infer them from public metadata.
4. Re-run all frozen v0.3.2 regressions and new 0.4.0rc1 packaging checks.
5. Require explicit new authorization for server provisioning or deployment.

**No live deployment is authorized by this research/development stage.**
