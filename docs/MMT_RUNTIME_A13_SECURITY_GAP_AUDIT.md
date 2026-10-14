# RUNTIME-A13 — authoritative A4–A12 source-security gap assessment

Baseline: main commit 16d88a62d3ca167a8ca66e93387915c138302656.
Scope: GitHub-only, nonproduction, static source audit and unit tests.
No real disposable host, independent witness/media or genuine OCI signer
was available. No Docker, unknown Worker, operational system or trading
engine was launched. Audit evidence is source-only, not a release certificate.

**VERDICT: RUNTIME_A13_SOURCE_CONTRACT_CHECKED_RUNTIME_NOT_CERTIFIED**

## Executive outcome

A6 contains an explicit unconditional denial in require_worker_launch.
A1 MultiLanguageOfflineHost.evaluate invokes it before touching the rootless
daemon or attempting _run_oci. A1 _run_oci also invokes it directly before
constructing the Docker command or spawning subprocess.Popen. These three
source-code invariants were present at baseline and are regression-checked.

A4-A12 carry separate review claims, supply-chain observations, replay
ledgers, locally chained evidence or simulated offline witness/recovery.
None provides separately proven, physically independent execution grant.
All security/permission booleans checked in review dataclasses default to
FALSE. The source scanner checks those defaults, not arbitrary caller code,
dynamic imports or runtime monkeypatches.

**No code or workflow is authorized to remove A6's unconditional stop.**

## Findings and acceptance gates

| ID | Severity | Finding / concrete evidence | Closure criterion |
| --- | --- | --- | --- |
| A13-G01 | RELEASE BLOCKER | A7 preflight only queries read-only host metadata, has not performed a real gVisor/rootless isolation experiment on a designated disposable host. | Independently designated expendable host, binary and image digest pins, operator signoff, actual containment/escape regression and verified original logs. |
| A13-G02 | RELEASE BLOCKER | A8 pins local source bytes and can verify supplied local OCI layers; existing A2 Dockerfile still uses a mutable Python base tag and unverified apt and package download artifacts. | Reproducible controlled build, base and dependency immutable digests, signed provenance/SBOM, offline artifact verification, independent issuer validation. |
| A13-G03 | RELEASE BLOCKER | A10 comparisons depend on externally supplied anchor. A11 witness SQLite and shared-key HMAC cannot independently prove a trusted latest receipt, immutable off-host custody or resistance to full rollback of both database and floor. | Separate independently controlled custody, authenticated monotonic latest-head pins, recovery and full rollback exercises with evidence stored across trust domains. |
| A13-G04 | RELEASE BLOCKER | A9 accepts a ConsumedReview Python instance rather than verifying a separately attested A5 ledger entry. Worker, source and request hashes are operator claims. | Independent end-to-end review attestation with measured artifact binding and transcript verification; never treat current review objects as grants. |
| A13-G05 | RELEASE BLOCKER | A12 dual HMAC proposal uses shared keys, a caller-retained floor, a claimed key epoch and an untrusted caller clock; separate proposals may fork and key retirement is not operational. | Independent signer enrollment, trusted monotonic epoch/floor, custody and two-person key rotation, stolen-key and fork recovery exercises. |
| A13-G06 | RELEASE BLOCKER | No stable trusted clock, no live host observation, no independent real-media witness or full real-world cross-machine recovery run. | Real approved environment, trusted time, documented external review and physical evidence, authorized security acceptance. |
| A13-G07 | ACCEPTANCE LIMIT | AST checking and green unit CI catch narrowly modeled mutations, not reflection, imports injected indirectly, dynamic monkeypatching, compromised GitHub runners or every possible security error. | Expert review plus negative differential tests, independent deployment boundary verification and separately authorized launch design. |

## Cross-stage trust model

- A4: HMAC authenticates **claims**, not the asserted host probe.
- A5: signed A4 review can be consumed locally once; its state is not an
  independently verified execution capability.
- A6: universal runtime launch denial remains mandatory at A1 entrypoints.
- A7: read-only, operator-invoked disposable-host observation; no real host
  attestation; read-only subprocess queries are not Worker execution.
- A8: source SHA256 plus optional offline OCI integrity; neither implies
  publisher identity, correct dependencies or safe image contents.
- A9: inert one-time review tickets; caller claims key, time, A5 review,
  Worker and source digest; no connected issuer identity authority.
- A10: local evidence hash-chain and explicit supplied-pin comparison;
  comparison cannot verify where the pin was kept.
- A11: local witness HMAC receipt chain and externally supplied floor;
  shared-key verification is not public-key signature or physical custody.
- A12: review-only two-key bridge, replacement genesis and lost-media block;
  neither actual key erasure nor independent monotonic state is provided.

## A13 additional automated checks

Module: naseri_markets/runtime_a13_security_contract_audit.py.
The auditor does not import Worker code, call the Docker API, create
containers, import third-party plugins or edit repository files. It reads
the nine fixed stage modules, A1 entrypoint and A2 Dockerfile, checks:
1. Exact unconditional A6 raise-deny shape, presence of preflight call and
   absence of any return/yield in require_worker_launch.
2. Direct A6 guard statements before command building and every modeled
   subprocess call in _run_oci, and before daemon/socket/_run_oci in evaluate.
3. Explicit false defaults for all controlled review permission/proof fields
   in A4–A12 source data classes.
4. Unexpected direct process/network library imports into nominally review-
   only modules. A7 is exempted from the import check because it has an
   intentionally read-only subprocess metadata probe.
5. Required source files, symlinks and parse validity.

Tests additionally mutate local copies to remove gates, change denial
exception types, insert a process before the guard, flip security flags,
inject executor imports, remove the Dockerfile and corrupt module text.
These are **regression guards only**. Any failed mutation test stops the
A13 workflow; passing them does not establish full security.

## Security disposition

RUNTIME: **DENY**. REAL GVISOR HOST ATTESTATION: **NOT_PROVEN**.
REAL EXTERNAL CHECKPOINT CUSTODY: **NOT_PROVEN**. KEY ROTATION SECURITY:
**NOT_PROVEN**. REAL EXECUTION GRANT: **NONE**.

No trading live/paper mode, broker, Telegram or quarantined Worker pathway
has been enabled. Do not automatically progress to a runtime launch or
production deploy based on this audit. The next useful work should be
closing independently verifiable external gates, not accumulating more
paper-only launch wrappers without source evidence.

On a real disposable host, re-run a separate, explicitly authorized
nonproduction, no-secrets isolation assessment before requesting any
change to A6.
