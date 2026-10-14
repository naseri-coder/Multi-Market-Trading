# CERT-A11 — Debian APT package archive closure hash lock (nonproduction)

## Authorized scope and status

This is a **GitHub-hosted CI-only** Worker candidate supply-chain hardening
stage. No TELMIVO / License Authority / trading servers are accessed, no
production deploy, database, broker, Telegram, or untrusted user code is run.
RUNTIME-A6 continues unconditionally denying Worker launches.

## Actual, observed Debian archive inventory

Disposable GitHub Actions on 2026-10-14 used the already digest-pinned
python:3.12-slim-bookworm OCI base, Debian's ordinary signed APT repository
metadata, and the fixed apt-get command for nodejs + npm with
--no-install-recommends. It downloaded 372 Debian package archives including
transitive dependencies into a separate APT cache; each archive was inspected
with dpkg-deb and hashed directly.

Full per-package name, exact Debian version, architecture, and SHA-256
archive digest are committed in:
deploy/runtime_a2/a11_apt_closure.json

The canonical closure SHA-256 (with fixed domain separation) is:
47bd698232b4f624d1aab35c6453e1f01641b1b6ebdd8d4d7dc38a4dd19ae872

The observed direct-package archive entries:
- nodejs 18.20.4+dfsg-1~deb12u3 (amd64), SHA-256:
  97d0944c0da81b0acd4c6d58e7d5a2894f89aa66067400a86c9ecb0b76969ecc
- npm 9.2.0~ds1-1 (all), SHA-256:
  1e31d6a0bd0bef04c2f1748ea776cd4e1f2c266ecf177c9539a8015e04d3a068

This lock is a reviewed **content equality** contract, not an independent
trusted Debian publisher key, timestamped snapshot, or source provenance.

## Actual Docker build enforcement

The A2 Dockerfile fetches from APT, downloads the fixed nodejs/npm dependency
closure into /tmp/mmt-a11-apt/archives, **does not install yet**, then runs
the fixed CERT-A11 helper to verify every downloaded .deb's actual SHA-256,
version, arch, name, strict count and exact full manifest.

Only after all 372 entries match will apt-get install using --no-download
and the same archive cache. Every installed dependency version is then
checked against the lock with dpkg-query. A mismatch aborts the build.

The Docker build context allowlist permits only the existing Worker file,
the existing Wasmtime lock, and two CERT-A11 fixed lock/helper files. No
secrets, source tree, keys, or unrelated files are made available to the
Docker build. Existing A8 source SHA lock is updated for the Dockerfile;
A10 archive checks and CERT-A8/A9 fixed harmless runtime tests remain.

## Important remaining limitations

1. The Debian mirror/index *time* is still **mutable**, and the exact APT
   snapshot or Debian Release/InRelease fingerprint is NOT pinned. An update
   to the mirror may cause a future build to fail closed, instead of fetching
   the original archived bits. This protects from silent drift but does NOT
   establish durable reproducible supply.
2. Signature validation is performed by ordinary Debian APT index handling,
   using keys available in the pinned base image. There is no independent
   signed Release/key custody, trusted timestamp witness, reproducibility
   attestation or independent publisher verification in CERT-A11.
3. The full final Worker OCI image remains unsigned, and no separately
   approved rootless/gVisor host confinement or hostile-input evaluation has
   occurred. GitHub-hosted rootful Docker fixture success cannot fill that.
4. A lock and source in the same Git repo are not independent immutable trust
   anchors. Base image index digest, npm TypeScript, Wasmtime wheel and Debian
   archive pins assert bytes only, not freedom from compromise/vulnerabilities.
5. The 372 entries are specifically for the fixed linux/amd64 pinned-base
   and APT state observed on 2026-10-14. Changing upstream APT availability,
   distro or architecture requires a separately reviewed new lock.

## Validation requirements

- CERT-A11 offline negative tests and real APT closure archive check PASS.
- Existing RUNTIME-A2 fixed four-language Docker image build PASS.
- Fixed benign Docker bounds, installed Worker SHA and versions PASS.
- RUNTIME-A6 denial and Publication safety PASS.
- Zero skipped tests or deviations in authorization.

**Acceptable verdict if all checks pass:**
CERT_A11_ALL_372_DEB_ARCHIVES_PINNED_APT_SNAPSHOT_AND_PUBLISHER_CUSTODY_OPEN

**Not acceptable:** claiming independent Debian upstream trust, reproducible
image promotion, gVisor host certification, user strategy execution, trading,
Telegram delivery or any A6 unlock.
