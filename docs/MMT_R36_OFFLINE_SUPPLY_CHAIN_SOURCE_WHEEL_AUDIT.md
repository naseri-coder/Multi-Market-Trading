# R36 — Offline Git-to-Wheel Provenance and RECORD Audit

**Scope: READ-ONLY public source / offline preview only.**
The Draft R36 branch is stacked on R35, and does not merge, publish,
rebuild, install services, activate brokers, execute external strategies,
access Telegram, or change production resources.

## Verified starting evidence

Operator-proven on Android/Termux Ubuntu 24.04 Python 3.12.3:
R34 public Wheel build, 31 A6/Stage15/PAPER tests, 135 selected R28-R34
tests, installed synthetic PAPER journaling and independent online SQLite
backup/recovery plus dedup; R35 Ruff and 14 unit tests, hash-pinned
non-root *functional* PRoot offline venv install, CLI check and four
negative installer denials. None is authorization for public/live release.
PRs R34 #327, R35 #328 and R36 remain unmerged Drafts.

## Security purpose and guarantees

The separate R36 verifier requires all of:

* A caller-supplied **independently recorded, exact** Wheel SHA256.
* A caller-supplied **independently reviewed exact Git commit SHA** of the
  R36 source checkout, with local public module and platform metadata
  paths clean including untracked files. Git checks use optional locks off.
* R35's bounded ZIP/member/metadata guards, no path traversal, private
  NYFR module or unexpected installed distribution identities.
* **Exact byte match** between each public \`naseri_markets/*.py\`
  module in the current clean Git checkout and the installed-capable
  Wheel; no extra modules and no unrecognized dist-info entries.
* Strict PEP 427 \`RECORD\`: all ZIP members listed exactly once, valid
  SHA256 and uncompressed size for every member except RECORD itself.
* The Wheel platform tag must be \`py3-none-any\`; its
  \`console_scripts\` must match every source pyproject entry point.
* Outputs a canonical logical payload SHA256 independent of timestamps
  and compression, and a canonical public-source-content SHA256.

This is **local byte-equivalence with independently supplied pins**,
not a signed SLSA/Sigstore/in-toto attestation, trusted build executor,
independent commit signature, secret-key signature or network isolation.
Neither the source commit nor its fingerprint becomes authentic merely
because the untrusted package says so. The expected SHA and source
commit must be taken from a *separate approved review channel* and not
extracted unquestioningly from a Wheel or its self-authored report.

No source or archive modification is performed. The only subprocess
calls are read-only Git head and status operations, with
\`GIT_OPTIONAL_LOCKS=0\`. This is not a sandbox for executing malicious
package code. All successful R36 verdicts keep production, broker,
Telegram, connected PAPER and LIVE denied.

## Stage 1 — Termux R36 local independent audit

The operator should create a **separate detached R36 worktree** while
retaining R34 and R35 successful checkout and Wheel. Run Ruff and the
R36 unit test module with the existing Python 3.12 test venv and the
same \`--noconftest\` isolation.

Use the Git SHA printed by \`git rev-parse HEAD\` *after checkout*
as \`--expected-source-commit\`, but verify that SHA against the
intended GitHub PR head in a separate authorized view. This is a
source-identity pin, not a cryptographic publisher attestation.

    export MMT_NONPRODUCTION=1
    unset MMT_PRODUCTION
    python -m scripts.mmt_r36_offline_release_provenance_v1 \
      --repository "$PWD" \
      --wheel /root/mmt-r34-wheel.7iTGsSLb/wheels/multi_market_trading-0.4.0rc1-py3-none-any.whl \
      --expected-wheel-sha256 a99553947fba0e6a848e1c9b5cdb144408b70f380c8f713f43a14b393c15bc8f \
      --expected-source-commit "<EXACT-INDEPENDENTLY-VERIFIED-R36-COMMIT>"

**Operator results are PENDING** until actual program output.
Do not call code tests automatically or auto-Merge.

## Stage 2 — optional independent second local Wheel comparison

\`--compare-wheel /absolute/path/to/second/whl\` independently
verifies the *second* Wheel against the same clean pinned source and
Wheel RECORD, then checks whether the normalized uncompressed payload
SHA256 matches. The program separately displays
\`second_wheel_identical_bytes\`; \`false\` must not be reported as
byte-reproducible even if payload digests agree.

The second builder's authenticity and isolation are not established
by this local comparison. Do not claim reproducible builds without
independently recorded build environments and external signed proof.

## Remaining release blockers

R27 Brooks frozen worker still deferred; Stage15 remains
\`PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE\` with nine P0 and
one P1 blockers. Independent real host/user isolation, hostile-plugin
containment, signed release identity and actual integrated runtime
acceptance must be separately established before any release.

## 2026-10-16 actual operator Termux source-to-Wheel audit — PASS

The operator ran the R36 read-only audit **using explicit
`/usr/bin/python3.12`**, version **3.12.3**, inside disposable
`/root/mmt-r36-lab` at Git SHA
`24519e919c3a11542ff34eed4a0afa1642656602`.
Initially their unqualified `python` resolved to Termux
`/data/data/com.termux/files/usr/bin/python`, which lacked Ruff and
pytest and caused `R36_OFFLINE_PY312_ONLY`: **this was an interpreter
mismatch, not a code-test failure**. The corrected explicit Python
3.12 invocation returned **`R36_AUDIT_EXIT=0`** with the genuine
JSON values:

```json
{
  "verdict": "R36_LOCAL_SOURCE_WHEEL_EQUIVALENCE_PASS_RELEASE_DENIED",
  "source_commit": "24519e919c3a11542ff34eed4a0afa1642656602",
  "source_module_bytes_match": true,
  "public_modules_verified": 221,
  "source_tree_sha256": "d3a42bf4e81b97775c7b2ca31161f59bcc5020a56ddb2f9935353bc51c9293d0",
  "wheel_sha256": "a99553947fba0e6a848e1c9b5cdb144408b70f380c8f713f43a14b393c15bc8f",
  "wheel_bytes": 787808,
  "wheel_payload_sha256": "a2fbe39808af358fd284240153bd331e67b1fae71bbe6d406004f3e530101659",
  "wheel_record_verified": true,
  "files_written": false,
  "publisher_signature_verified": false,
  "independent_provenance_verified": false,
  "production_release_authorized": false,
  "live_authorized": false
}
```

**Bounded acceptance:** actual operator
`R36_LOCAL_SOURCE_WHEEL_EQUIVALENCE_PASS_RELEASE_DENIED`
for the *one* source/Wheel pair. **Still pending:** Ruff and pytest
execution of the 12 new negative R36 unit tests using the previously
installed Python 3.12 test venv, and any second-Wheel comparison.
Do not interpret this as an authenticated publisher signature,
independent build attestation, deterministic rebuild, release
authorization, connected market access or permission to merge.

R34, R35, R36 remain Draft and unmerged; Stage15 P0/P1 and deferred
R27 Brooks evidence unchanged.
