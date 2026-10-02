# Exact legacy Ruff baseline for new paths

The normal ratchet remains `HEAD_COUNTER - BASE_COUNTER`. Existing published
files cannot receive an exemption, including files with historical registry
entries. The workflow invocation and Ruff configuration remain unchanged.

`production_checks/ruff_legacy_path_baseline.json` starts with schema version 1
and an empty `entries` list. Future source publication must explicitly review
every added entry; this architecture change accepts no legacy source debt.

## Entry contract

Each entry contains exactly `path`, `sha256`, and `findings`. The path must be a
canonical repository-relative file under `production_source/`,
`production_checks/`, or `scripts/`. The SHA256 is 64 lowercase hexadecimal
characters and pins the exact head bytes. Each finding record contains exactly
`code`, `message`, `context`, and a positive integer `count`.

Generate records from Ruff 0.16.9 with the current head configuration, using the
ratchet's `_counter` and `_fingerprint` functions. The fingerprint includes the
relative path, code, message, and the diagnostic line with up to two textual
lines before and after it. Record every fingerprint and its exact multiplicity,
sorted deterministically; never substitute aggregate code totals or row numbers.
Do not register clean files, store whole files, or include secret content.

An exemption applies only when the path is absent from the exact comparison
base, is a regular nonsymlink file in head, its byte hash matches, and its entire
actual finding Counter equals the registered Counter. Missing or additional
findings, changed context, changed bytes, invalid data, and duplicate records
fail closed. Unregistered new debt still fails normally.

Once the file exists in base, the entry is historical and contributes zero
exemptions. Its old hash and findings do not suppress future regressions.
Historical records must still be structurally valid. Keep or remove them through
an explicit reviewed change; no registry update is required for ordinary edits.

The historical 348-entry production source manifest is a separate integrity
contract. This registry neither expands that manifest nor authorizes publication.
Audit output reports registry entries, applied paths, applied findings, and the
remaining new findings without printing registered source context.
