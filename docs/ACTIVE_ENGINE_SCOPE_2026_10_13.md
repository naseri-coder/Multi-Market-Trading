# Trading-core scope — 2026-10-13

The only strategy workstreams currently selected are public Al Brooks Price Action and private-owner NY First-Reversal R0 / First Follow-up V1. The NYFR source stays in its separate private repository. None is newly deployed or enabled by this change.

Removed from active source and public catalog:
- The unimplemented FM runtime, registry, coordinator and Telegram management choice. Historical applied migration 20261004_0022 and legacy database CHECK constraints remain unchanged because rewriting deployed migration history or deleting operator data would be unsafe. Previous FM rows, if any, are excluded from the admin listing; application strategy commands now allow BROOKS only.
- The public DualSetupExampleCore strategy sample, its module and public strategy identity. Existing synthetic pipeline tests retain a private-by-convention _contract_acceptance_fixture_v1.py internal fixture with a different ID and no trading/live authorization, so regression coverage is not deleted.

Unchanged: Public Custom Engine/SDK/adapters/plug-in infrastructure, Brooks trading logic, NYFR private source, production servers, databases and credentials. The new nonproduction staging source has a regenerated checksum manifest and updated shape assertions (358 entries, not the previous 362). The Brooks PAPER adapter's independently reviewed manifest SHA-256 pin and entry-count gate are updated to the exact new source tree; the actual Brooks strategy formula is not modified. No database migration or production rollout is performed.

Do not count any internal deterministic offline fixture as a strategy engine. Source-level import/compile and checksum preflights are distinct from integration and production acceptance.
