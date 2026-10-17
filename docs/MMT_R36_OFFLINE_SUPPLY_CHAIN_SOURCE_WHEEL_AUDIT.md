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

## 2026-10-16 actual operator isolated Ruff and negative unit suite — PASS

Operator confirmed:
- Existing Ubuntu/Termux `mmt-r34-lab` PRoot, Python 3.12.3.
- `/root/mmt-r36-lab` exists as detached worktree and had clean `git status --short`.
- Existing test venv `/root/mmt-r34-venv/bin/python` has Ruff **0.16.9** and pytest **9.1.1**.
- Real Ruff execution on `scripts/mmt_r36_offline_release_provenance_v1.py` and
  `tests/unit/test_mmt_r36_offline_release_provenance_v1.py`:
  **`All checks passed!`**.
- First standalone pytest attempt failed on repository-level unknown config
  option `asyncio_mode` because automatic third-party plugin loading was
  deliberately disabled; **no tests were executed** in that attempt.
- Operator reran `pytest -c /dev/null -q -p no:cacheprovider --noconftest`
  on the exact R36 test module with
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and
  `PYTHONDONTWRITEBYTECODE=1`: **`13 passed in 3.79s`**,
  **`R36_TEST_EXIT=0`**, and `git status --short` empty.
  The 13 selected pytest cases correspond to the new 12 test functions
  including one 2-case parameterized test.

**Bounded status:** `R36_REAL_GIT_WHEEL_AUDIT_PASS`,
`R36_RUFF_PASS`, `R36_NEGATIVE_TESTS_13_PASS`.
The earlier `pytest` error was a test harness/plugin configuration
issue resolved by invoking only the isolated R36 unit module, **not**
by removing tests or weakening supply-chain gates.

**Remaining evidence:** A *second local build* from a new staging
directory has **not yet** been performed. The optional second-Wheel
comparison can distinguish source-equivalent uncompressed package
members from full byte-for-byte reproducibility. Building a second
archive with the same local toolchain is **not** an independent builder,
verifiable attestation, hostile build isolation or release certificate.
Maintain the strict Draft/unmerged P0/P1 and LIVE/production denials.

## 2026-10-16 second local Wheel build attempted — blocked at toolchain preflight

The operator fast-forwarded the detached R36 source checkout to
`f1c48708b1fc320a26066c2d383ff620901b0448`
and started the suggested **second local Wheel** procedure.

The first build-toolchain metadata query on
`/root/mmt-r34-venv/bin/python` failed **before creating a staging
directory or running a package build**:

```text
=== BUILD TOOLCHAIN ===
importlib.metadata.PackageNotFoundError:
No package metadata was found for setuptools
R36_BUILD_EXIT=1
```

The earlier R36 real source/Wheel audit, Ruff and 13 isolated unit
tests remain valid. **No second Wheel exists from this invocation**.
Do not mark payload equivalence, archive byte reproducibility, supply
chain signatures, or packaging acceptance as achieved.

Next operator diagnostic (read-only) must inspect existing Python 3.12
environments for *both exact pinned* build dependencies from
`platform_release/pyproject.toml`:
`setuptools==80.9.0`, `wheel==0.45.1`. Inspect existing local cached
Wheels (if any) without downloading, installing into the successful
test environment, modifying R35/R36 source or waiving the pins.
If absent, retain `R36_SECOND_BUILD_TOOLCHAIN_UNAVAILABLE` and
`R36_SECOND_BUILD_PENDING`; the final PR remains Draft and
release/live denied.

## 2026-10-16 pinned offline build tools acquired and SHA-checked — PASS

The operator ran a separate, authorized **PyPI download** of the
exact public build-tool requirements from
`platform_release/pyproject.toml` into a new private directory.
Their observed environment and verification output were:

```text
TOOLCHAIN_AREA=/root/mmt-r36-toolchain.KC3cP1Ft
setuptools-80.9.0-py3-none-any.whl: OK
wheel-0.45.1-py3-none-any.whl: OK
R36_PINNED_TOOLCHAIN_ACQUIRED
R36_ACQUISITION_EXIT=0
```

The independently supplied SHA256 pins used for verification were:
- `setuptools==80.9.0`:
  `062d34222ad13e0cc312a4c02d73f059e86a4acbfbdea8f8f76b28c99f306922`
- `wheel==0.45.1`:
  `708e7481cc80179af0e556bbf0cc00b8444c7321e2700b8d8580231d13017248`

The downloaded artifact path is:
`/root/mmt-r36-toolchain.KC3cP1Ft/wheelhouse`.
No build or full package comparison has yet occurred. The next step
must keep the successful R34 Ruff/pytest venv and the reference Wheel
untouched, create a **new** Python 3.12 build venv, install precisely
these two **locally available** pinned Wheels with
`pip --no-index --no-deps --require-hashes`, then stage public
sources with A6 and rebuild using
`pip wheel --no-build-isolation --no-index --no-deps`.
Validate the second Wheel using R36 against the original independently
pinned source SHA and original Wheel SHA. The build result and
reproducibility verdict remain **PENDING**.

The download step used PyPI network access, but the upcoming
installation and second build are strictly offline by explicit pip
flags. No producer signature or independent builder is established;
Stage15 release and LIVE remain denied.

## 2026-10-16 actual operator second Wheel verification — content PASS / byte mismatch CONFIRMED

Operator completed a new build using the previously SHA256-checked
`setuptools==80.9.0` / `wheel==0.45.1` pins, in isolated
`/root/mmt-r36-rebuild.pHGewHBu`, without touching the reference
Wheel or successful unit-test venv. Actual operator terminal showed
`R36_SECOND_BUILD_COMPLETED` and `R36_BUILD_EXIT=0`.

An explicit subsequent **read-only** comparison against the original
R34 Wheel from the clean R36 checkout at
`0cfc469d8fd150e1a6bb7a10c76c3914fce6a033`
produced these independent `sha256sum` values:

```text
ORIGINAL SHA256:
a99553947fba0e6a848e1c9b5cdb144408b70f380c8f713f43a14b393c15bc8f
REBUILD SHA256:
79c22e89bf04c10e30029af0d2d84ddd23674a5d9514b77e2e196b92d3f01526
cmp: R36_WHEEL_BYTES_DIFFER
```

The operator then invoked
`scripts.mmt_r36_offline_release_provenance_v1` with
`--compare-wheel` targeting the second local artifact. Verified
JSON values:

```json
{
  "verdict": "R36_SECOND_WHEEL_PAYLOAD_EQUAL_BYTES_DIFFER_RELEASE_DENIED",
  "source_commit": "0cfc469d8fd150e1a6bb7a10c76c3914fce6a033",
  "source_module_bytes_match": true,
  "public_modules_verified": 221,
  "source_tree_sha256": "d3a42bf4e81b97775c7b2ca31161f59bcc5020a56ddb2f9935353bc51c9293d0",
  "wheel_sha256": "a99553947fba0e6a848e1c9b5cdb144408b70f380c8f713f43a14b393c15bc8f",
  "wheel_bytes": 787808,
  "wheel_payload_sha256": "a2fbe39808af358fd284240153bd331e67b1fae71bbe6d406004f3e530101659",
  "wheel_record_verified": true,
  "second_wheel_sha256": "79c22e89bf04c10e30029af0d2d84ddd23674a5d9514b77e2e196b92d3f01526",
  "second_wheel_same_payload": true,
  "second_wheel_identical_bytes": false,
  "files_written": false,
  "publisher_signature_verified": false,
  "independent_provenance_verified": false,
  "production_release_authorized": false,
  "live_authorized": false
}
```

The session ended with `R36_FINAL_VERIFICATION_COMPLETED`,
`R36_FINAL_EXIT=0` and clean `git status --short`.
**The tool's zero exit code means the verified payload was equal;
it does NOT mean byte-for-byte archive reproducibility.**

Disposition: `R36_OPERATOR_LOCAL_SOURCE_PAYLOAD_AND_SECOND_BUILD_PASS`
but `R36_WHEEL_BYTE_REPRODUCIBILITY_NOT_PROVEN`. Archive byte
differences remain; likely sources include ZIP metadata timestamps,
file ordering, compression settings or other ZIP headers. These are
**hypotheses**, not verified causes. Follow-up may read both ZIP
central-directory entries and headers to identify the exact difference
without rebuilding or modifying either artifact. Keep Draft/unmerged;
publisher authenticity, independently isolated trusted builder,
Stage15 P0/P1, deferred R27 Brooks and production/LIVE deny gates
unchanged.

## 2026-10-16 actual operator ZIP metadata differential — only DOS date/time fields differ

Using Python 3.12.3 standard-library `zipfile` with **no writes**,
the operator compared exact original R34 Wheel
`a99553947fba0e6a848e1c9b5cdb144408b70f380c8f713f43a14b393c15bc8f`
and R36 rebuilt Wheel
`79c22e89bf04c10e30029af0d2d84ddd23674a5d9514b77e2e196b92d3f01526`.
The actual output was:

```json
{
  "verdict": "R36_READONLY_ZIP_DIFF_DIAGNOSTIC",
  "members": 226,
  "content_differences": 0,
  "member_order_identical": true,
  "metadata_differences": {
    "date_time": 226
  },
  "first_affected_member_by_field": {
    "date_time": "multi_market_trading-0.4.0rc1.dist-info/METADATA"
  },
  "archive_comment_identical": true,
  "files_written": false
}
```

The audited per-member metadata fields were `date_time`,
`compress_type`, `compress_size`, `CRC`, `external_attr`,
`internal_attr`, `flag_bits`, `header_offset`, `create_system`,
`extra`, and `comment`. Only `date_time` differed, for **all 226
members**. This strongly isolates the differing ZIP timestamp metadata
as the archive byte-mismatch cause within the examined fields; no
claim is made that every raw header byte has been exhaustively diffed.
Source module equality, member order, metadata checks, RECORD integrity,
and 13 R36 unit tests remain successful.

**Next bounded reproducibility experiment (PENDING):** create **two
fresh separate A6 public-source staging folders**, keep the exact
verified offline build toolchain `setuptools==80.9.0` /
`wheel==0.45.1`, set a fixed `SOURCE_DATE_EPOCH=1704067200`,
and build each with explicit offline pip flags into private separate
Wheel directories. Compare third versus fourth Wheel SHA256/cmp and
run the R36 verifier against the verified Git commit. Never overwrite
the R34 reference or the already-tested R36 second archive. A
byte-identical pair would demonstrate **same-host local reproducible
builds with fixed timestamp**, *not* make the older unstabilized R34
archive retrospectively identical, create independent publisher
authenticity, or close any production/LIVE Stage15 blockers.

## 2026-10-16 operator fixed-epoch *same-host* byte-for-byte reproduction — PASS

After the exact build-toolchain pins `setuptools==80.9.0` and
`wheel==0.45.1` were acquired and SHA-verified, the operator ran
**two newly staged offline builds** in separate private directories,
using a distinct pinned Python 3.12 build venv and the controlled
environment `SOURCE_DATE_EPOCH=1704067200` and `PYTHONHASHSEED=0`.
The source checkout used the verified previous document commit
`cf0b2e86aa7b1223e3180449a0eada164d3ee088`.
The original R34 Wheel and the earlier unequal R36 rebuild were
not overwritten. The operator reported:

```text
TEST_AREA=/root/mmt-r36-deterministic.HMdBVILp
R36_DETERMINISTIC_BUILD_CHECK_COMPLETED
R36_TEST_EXIT=0
```

A **separate read-only byte-level verification** then compared the
two third/fourth-build artifacts directly:

```text
=== TWO BUILD SHA256 ===
37c18d73978ecc48febc3a56e79b8ac65da6d77bce7b18ea68db44212c2c5ee4  /root/mmt-r36-deterministic.HMdBVILp/wheels1/multi_market_trading-0.4.0rc1-py3-none-any.whl
37c18d73978ecc48febc3a56e79b8ac65da6d77bce7b18ea68db44212c2c5ee4  /root/mmt-r36-deterministic.HMdBVILp/wheels2/multi_market_trading-0.4.0rc1-py3-none-any.whl
=== EXACT BYTE COMPARISON ===
R36_FIXED_EPOCH_BYTES_IDENTICAL
=== SOURCE STATUS ===
[empty git status --short]
R36_BYTE_CHECK_COMPLETED
```

**Accepted narrowly:** `R36_SAME_HOST_FIXED_EPOCH_BYTE_REPRODUCIBILITY_PASS`.
The two new artifacts are identical byte-for-byte, as established
by both SHA256 and `cmp -s`, not merely logical payload equality.
This closes the bounded local fixed-timestamp reproduction experiment,
**but does not make the older R34 original Wheel hash match these
new artifacts**. The earlier
`R36_SECOND_WHEEL_PAYLOAD_EQUAL_BYTES_DIFFER_RELEASE_DENIED`
remains a true observation about the unfixed-timestamp pair, whose
ZIP metadata `date_time` differed on all 226 entries.

Limits: same Android/Termux PRoot host, same build venv and Python
toolchain, fixed `SOURCE_DATE_EPOCH`; **no trusted independent
builder, signed build manifest, upstream signature verification, real
host isolation, supply-chain attestation or public-production
authorization**. The GitHub PRs remain Draft and unmerged; R27
frozen Brooks smoke and Stage15 nine P0 plus one P1 remain blocked.
Continue to deny broker orders, connected PAPER, Telegram delivery,
private NYFR distribution and LIVE.
