# RUNTIME-A8 — offline Worker supply-chain integrity

**Scope:** GitHub source-only, nonproduction. **No** host/production changes, network
downloads, Docker launch, package install or worker authorization.

## Findings (exact reviewed baseline)

At GitHub main `85be31fdfef95fc5fe384dc2961dbb9a7f51160b`, the candidate
`deploy/runtime_a2/Dockerfile` still uses:

- `FROM python:3.12-slim-bookworm` (mutable tag, no immutable base digest).
- `apt-get install nodejs npm` (repository state and binary versions not frozen).
- `typescript@5.9.3` (version only; package tarball integrity/provenance not pinned).
- `wasmtime==49.0.0` (version only; wheel hash / provenance not pinned).

The existing candidate image has **not** been verified as a signed,
independently produced, rootless/gVisor-certified worker image. Do **not**
invent an OCI digest or treat fixed version strings as verified binary hashes.

## Implemented now

The file `deploy/runtime_a2/a8_source_lock.json` pins the **actual SHA-256
bytes** of the current Dockerfile, A2 Worker and A1 dispatch module. The
`verify_source_lock` function detects mutations to those files, rejects
unexpected schema keys, reordered/extra source entries, forged execution
authorization, path traversal/symlinks and mismatched SHA-256.

`verify_local_oci_layout` additionally verifies a **fully local** OCI v1
layout: fixed schema, exact out-of-band manifest SHA-256, single manifest,
config/layer type and descriptor sizes, then streams every referenced blob
and compares its SHA-256. It never pulls or executes a container. The
function is prepared for a future independently supplied OCI directory;
**none is included** in this repository, and CI only uses tiny fake fixtures.

A source manifest controlled by the same Git repository does **not** prove
publisher identity: an attacker who can change both file and lock can
replace both. OCI blob integrity similarly cannot attest signer identity,
absence of malicious contents, reproducible builds, or genuine runsc
confinement. Trusted signatures, verified dependency artifacts, independent
custody, a dedicated disposable host and real containment tests are
**future prerequisites**.

## Validation

```sh
PYTHONPATH=production_source:. python -m pytest -q \
  tests/unit/test_runtime_a8_supply_chain.py \
  tests/unit/test_runtime_a6_dispatch_fence.py \
  tests/unit/test_runtime_a7_disposable_host_preflight.py
```

This stage does not modify the legacy wheel, migrations, Dockerfile,
package requirements, trading engines or original A2 worker; it only
introduces a fail-closed **review**, not a runnable release.

**Verdict: `RUNTIME_A8_SOURCE_LOCK_PREPARED_EXTERNAL_PROVENANCE_BLOCKED`.**
