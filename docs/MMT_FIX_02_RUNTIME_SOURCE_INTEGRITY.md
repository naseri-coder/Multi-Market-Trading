# MMT-FIX-02 — Runtime source inventory (B-01)

## Scope
The v0.3.2 `production_source/SHA256SUMS` contains exactly 359 frozen files and
must retain its original SHA-256 digest `1a15f9d4...`. Brooks Replay independently
pins that manifest and the original three public cold-start modules.

`scripts/verify.sh` now invokes `scripts/verify_runtime_integrity.py` after
the historical SHA256SUMS check. The new check maintains **separate exact SHA-256
pins** for the three previously unlisted modules, checks all 359 manifest
entries, and enforces an exact runtime Python inventory (356 frozen Python
files + 3 pinned public additions = 359). Unexpected Python source files,
missing or changed public additions, and symlinks fail closed. The frozen
manifest, Brooks engine files and Production runtime are unchanged.

## Acceptance evidence
`tests/unit/test_runtime_source_integrity_fix02.py` exercises the genuine
checked-in tree plus disposable copies with mutations: three changed extra
files; three removed extra files; unlisted Python injection; extra-file and
directory symlinks; frozen source mutation; manifest mutation. It also
asserts that both independent pin lists agree without importing or executing
the Brooks engine.

Run `bash scripts/verify.sh` and `python -m pytest -q
tests/unit/test_runtime_source_integrity_fix02.py`. Required GitHub checks
must succeed before merging.

## Limitations and safety boundary
This is a **repository/CI integrity guard, not an independently signed
release attestation**. An actor capable of changing both the verifier and its
CI configuration could alter these in-repository pins; signing and external
trust anchors are distinct release-security concerns. The check validates
the runtime's tracked Python source, not arbitrary data/assets, dynamically
loaded third-party dependencies, or already-running production instances.
Neither a production server nor a trading engine is started by this change.
