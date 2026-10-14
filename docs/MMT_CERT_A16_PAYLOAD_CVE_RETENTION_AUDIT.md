# CERT-A16 — Actual runtime bytes vs Grype disappearance (read-only)

**Scope:** evidence-only nonproduction audit. Original Worker, base A2 and lean
A15 Dockerfiles, package/snapshot locks, trading, TELMIVO, production servers,
registry promotion and the unconditional RUNTIME-A6 DENY are unchanged.

## Authoritative comparison inputs

All files originated from one successful GitHub Actions run:
https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38597245244

- A2 baseline: artifact 11913190088, CycloneDX SBOM and Grype raw scan.
- A15 lean: artifact 11913135136, CycloneDX SBOM, Grype raw scan and
  pairwise comparison JSON.
- Both reports name Grype DB build 2026-10-14T06:30:34+00:00.
- Baseline image ID: sha256:30fba7e708d24c725c31e2e7bf2c774cf5776f33ddd01f0f36af462306e1acb4
- Lean image ID: sha256:6fdf364e5f8ec20d08c9e3e511520a58fe5dc094378628079931ebf5c96210d6

## Direct observations from actual JSON

| Metric | A2 baseline | A15 lean |
| --- | ---: | ---: |
| SBOM file components | 27,069 | 3,244 |
| SBOM package/library components | 2,078 | 113 |
| Scanner Critical matches | 18 | 3 |
| Scanner High matches | 181 | 67 |
| Scanner Critical + High matches | 199 | 70 |
| All scanner matches | 584 | 306 |

There are 3,243 identical pathname keys among the two actual CycloneDX
file inventories. Of these, **3,242 have identical SHA-256 bytes**; the one
different common path is `/var/lib/dpkg/status`, which is a metadata index,
not executable proof. This is **strong evidence that a scanner-count reduction
does not imply a code-byte change**.

Of the original 199 Critical/High package-specific Grype match identities,
70 still match by advisory, package type, package name and exact version;
129 no longer match that exact identity. A missing match is NOT a verified
fix or deletion. In particular, 10 Debian `node-undici` advisories from
A14 disappear from the Debian-classified scanner matches while npm
`undici` remains detected separately. The A15 export recipe explicitly
copies `/usr/share/nodejs/undici` as runtime code.

Critical CVEs in baseline and lean:
- CVE-2026-5450: libc-bin and libc6; both still reported as Critical.
- CVE-2025-7458: libsqlite3-0; still reported as Critical.
- CVE-2026-13697 and CVE-2026-84961: Debian node-undici; no longer
  reported under that exact Debian package identity, but its runtime code
  is deliberately carried into lean. Neither is certified fixed.

## New real file-byte evidence gate

`scripts/ci_cert_a16_payload_audit.py` now runs after A15 has built and
scanned both images on the **same disposable GitHub-hosted runner**.
It uses only `docker container create` (NO start) followed by
`docker cp -L` of an exact fixed list of files, then removes containers.
No script/Worker/unknown code starts or executes during this audit.

The fixed sampled byte paths include the real libc and SQLite shared
libraries, /usr/bin/node, libnode, libuv, and Debian's externalized undici
bootstrap file and package.json. For each image it records exact SHA-256,
enforces that Docker image IDs do not change and cross-checks CyconeDX
SHA-256 wherever available.

The audit additionally checks that all actual A2/A15 scan and SBOM SHA-256
digests match the A15 comparison evidence, the Grype DB timestamp is
identical, and all source report counts reconcile. Then every original
Critical/High finding receives exactly one **evidence** class:

1. SAME_ADVISORY_PACKAGE_VERSION_DETECTED_IN_LEAN
2. NOT_SCANNER_MATCHED_SAMPLED_PAYLOAD_BYTES_RETAINED
3. NOT_SCANNER_MATCHED_PAYLOAD_REMOVAL_UNPROVEN

All three categories retain `security_review_state=OPEN`,
`cve_fixed=false`, `false_positive_confirmed=false`.
An identical sampled file can establish only that these specific bytes
are retained: it cannot establish a whole package or vulnerability is
present and reachable, or decide whether backports fix its code path.
Unprobed files must remain UNKNOWN, not removed.

The real audit JSON is uploaded for three days and must be reviewed
before any subsequent A17 package-remediation authorization.

## Residual blocked items

- 199 original Critical/High scanner observations remain **OPEN**.
- Precise Debian upstream package-to-file ownership, security backports
  and exploitation preconditions still need independent case-by-case
  authoritative evidence; scanner metadata alone cannot decide them.
- Rootless Docker+gVisor independent host certification, signed image
  custody, and hostile-code containment remain NOT VERIFIED.
- Worker launch and production/broker/Telegram permissions remain DENIED.

**Verdict when CI passes:**
CERT_A16_BYTES_TRACED_ALL_ORIGINAL_FINDINGS_OPEN_RELEASE_DENIED.
