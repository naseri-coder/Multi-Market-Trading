> Historical reference only; not current release proof.
> Original source: `integration_phase1/docs/known_gaps.md`; SHA256: `e2e3bb9c22795e1cb2bd4e476c27968c1098950655e668df2e1f14eb76b9c311`.

# Integration Phase 1 — Known Gaps / Blockers

1. Existing public queries do not yet filter `publication_scope`.
2. Existing win-rate query does not yet filter `counts_toward_performance`.
3. No integration repository/service exists yet for `signal_automation_metadata`.
4. No PostgreSQL model classes exist yet for the two proposed tables.
5. `SignalDecision` does not carry `configuration_version`; integration must supply a versioned config hash/version.
6. Brooks Core does not supply leverage; integration config must supply it explicitly.
7. Real Telegram transport and signal-engine service wiring are later phases.
8. Proposed migration is a reviewed draft only; it has NOT been applied to the user's database.
