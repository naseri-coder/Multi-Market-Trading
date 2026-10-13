# Trading-core scope — 2026-10-13

The only strategy workstreams currently selected are public Al Brooks Price Action and private-owner NY First-Reversal R0 / First Follow-up V1. The NYFR source stays in its separate private repository. None is newly deployed or enabled by this change.

Removed from active source and public catalog:
- Retired unimplemented strategy runtime, registry, coordinator and Telegram management choice. The earlier applied migration and stored records remain for database compatibility. Retired records are excluded from the admin listing; the active application allows BROOKS only.
- Retired public instructional trading sample, its module and public strategy identity. Synthetic pipeline tests retain a renamed internal contract acceptance fixture with no trading/live authorization.

Unchanged: Public Custom Engine/SDK/adapters/plug-in infrastructure, Brooks trading logic, NYFR private source, production servers, databases and credentials. The new nonproduction staging source has a regenerated checksum manifest and updated shape assertions (358 entries, not the previous 362). The Brooks PAPER adapter's independently reviewed manifest SHA-256 pin and entry-count gate are updated to the exact new source tree; the actual Brooks strategy formula is not modified. No database migration or production rollout is performed.

Do not count any internal deterministic offline fixture as a strategy engine. Source-level import/compile and checksum preflights are distinct from integration and production acceptance.
