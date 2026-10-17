# CERT-A19-R26 — UTC Contract, Timezone Database Need, and Four-Language Runtime Resource Audit

**Independent narrow verdict:** \`WORKER_CORE_AWARE_UTC_STATIC_CONTRACT_PASS__TZDB_GUEST_DETERMINISM_AND_FOUR_LANGUAGE_RUNTIME_NOT_CERTIFIED\`

**Scope:** standalone **read-only static source/OCI-evidence review**. NO package mutation, tzdata installation, new Worker image, guest code execution, source modification to main, PR merge or production deployment.

## 1. Actual GitHub-hosted proof and unmodified source custody

- **Successful scoped GitHub Actions run:** [#38689110409](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38689110409), non-PR scratch branch \`cert-a19-byte-audit-run\`. **SUCCESS**, exactly one narrow audit job.
- First trial [#38689041456](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/38689041456) **failed closed** because the inspector mistakenly expected double quote characters from Python \`ast.unparse\` when it emits single quoted strings. Narrowly corrected the inspector; **no Worker or source edits**. Do not misinterpret this as a timezone/runtime incompatibility.
- Successful evidence artifact **11952225103**, name \`cert-a19-r26-utc-timezone-fourlang-readonly\`, **2-day retention**, downloaded independently. Exact output \`r26-timezone-contract.json\`: **5,448 bytes**, SHA-256 **\`2de79cd86da7ccc17ce15952455c8b7673cf4161d3f99a32955d668e7e9f1667\`**. Only JSON uploaded, not any executable.
- Restored R25 real composed-OCI evidence \`r25-static-final-oci.json\` SHA-256 **\`26bc9c72b4b49c396a973b783764875566f24b4b2568f9495032ad9dc51f9264\`** and R24 final overlay source \`r24-result.json\` SHA-256 **\`284ccd9f9549fbcd6572c442cc5f9ebf5759d4cdf5ccb419f2235bff8a3e2f61\`**. Rehashed original bytes before assessment.
- Reconfirmed R25 source: **40 installed Wolfi packages**, **153 ELF statically examined**, signed base OCI \`cgr.dev/chainguard/wolfi-base@sha256:256c88bb066424045021090932d50be93c8e3f2ce3586707702a401b146f3e43\`. R25's final merged file inventory has \`etc/os-release\` with \`ID=wolfi\`, and CA bundle \`etc/ssl/certs/ca-certificates.crt\`, but \`usr/share/zoneinfo/UTC\` **NOT FOUND**. This is a *source file inventory*, not a functional timezone/CA/TLS test.
- Inspector used \`ast.parse\` and immutable Git source blob byte checks (not \`import\`, not \`exec\`) for **eight unchanged main-branch source files**: \`scripts/runtime_a2_worker.py\`, \`naseri_markets/core_api_v1.py\`, \`naseri_markets/secure_plugin_runtime_v1.py\`, \`naseri_markets/multilang_runtime_a1.py\`, \`naseri_markets/runtime_a6_dispatch_fence.py\`, original \`deploy/runtime_a2/Dockerfile\`, \`Dockerfile.a15-lean\` and \`a15_export_runtime.py\`. All eight matched their exact original Git blobs. Full SHA-256 values for each are in the archived report.
- No source code, original images, old Debian 372-item A11 lock, A2/A15/A18 Dockerfiles, deployment resources, A6 policy or \`main\` changed; no production/trading/Telegram/TELMIVO effects.

## 2. Does the fixed core *require* IANA timezone files?

**Observed static answer: the *fixed original host/core UTC-normalization pathway* does NOT directly call system \`tzdata\`/Python \`zoneinfo\` or look up named IANA zones. It accepts a date/time already carrying an explicit offset.**

- In \`naseri_markets/core_api_v1.py\`, \`_utc\` rejects naive \`datetime\` values (missing tzinfo or UTC offset) and normalizes aware timestamps by \`value.astimezone(datetime.UTC)\`. \`CoreInput\`, \`CoreResult\` and timestamps use this core validation. This particular conversion from explicit offset to UTC does not need a named IANA-zone database lookup.
- In \`naseri_markets/secure_plugin_runtime_v1.py\`, \`_when\` calls \`datetime.fromisoformat\`; downstream CoreResult's aware UTC contract still applies. The inspector confirms this **code contract**, not every possible malformed clock or legacy timestamp regression.
- In \`scripts/runtime_a2_worker.py\`, the \`observed_at\` field in the outgoing result is copied from the digest-validated input event; the fixed framing code does **not** query a local timezone or convert event timestamp itself.
- In \`naseri_markets/multilang_runtime_a1.py\`, the host's child-I/O deadline uses \`time.monotonic()\`, not wall-clock timezone conversion.
- The existing historical A2/A15 Dockerfiles do not explicitly install \`tzdata\` or set \`ENV TZ\`. Their absence is not evidence that all possible user strategy features work without IANA data.

**Critical distinction:** Python/Node/TypeScript guest code can choose to perform timezone conversions, invoke date libraries, use JavaScript \`Date\` or \`Intl\`, or depend on a named zone such as \`Europe/Berlin\`. Static review **cannot prove this future arbitrary code is timezone-independent**, and the Node JavaScript host may use ICU timezone data that is NOT equivalent to \`/usr/share/zoneinfo\` being present. **Do not certify guest behavior as UTC deterministic or secretly turn off named-zone support.**

**R26 decision:** **No \`tzdata\` installation is authorized or justified solely by the fixed UTC core path.** First decide the explicit operator-facing guest timezone contract (UTC-only vs named-zone support) and constrain/test it in an independently safe fixture environment. If named-zone support is required, authenticate and pin a timezone package for the *exact signed Wolfi index and closure*, repeat byte and OCI/static verification, and test daylight-saving transitions. Do not silently use a mutable package index.

## 3. Four-language program and runtime-resource contract

| Language / layer | Verified from main source | R25 source-only status | Unpassed blocker |
|---|---|---|---|
| Python 3.12 | Worker invokes \`sys.executable -I -S -c PY_CHILD\`; child uses \`exec(compile(...))\` and requires a list of decisions | Native Python ELF present in composed Wolfi OCI | No actually executed benign Python fixture; no approved independent secure host |
| JavaScript | Worker invokes Node with \`--input-type=commonjs --eval\`, uses \`node:vm\` and \`vm.Script\` | Node.js 24 present, old A15 source pinned Node **18.20.4** | **Node 18→24 semantic parity not tested**; \`node:vm\` is not a security boundary |
| TypeScript 5.9.3 | Worker uses \`require('typescript')\` and \`transpileModule\` to target ES2022 | **Not installed** in R25 Wolfi image (R19 npm SHA-512 custody only) | Source authenticity/publisher attestation gap; actual compiler loading and fixture behavior not tested |
| Wasmtime 49.0.0 | Python imports \`wasmtime\`; denies imports in guest WASM, uses fuel and memory limits | **Not installed** in R25 Wolfi image (R19 PyPI wheel checksum only) | Independent origin attestation absent; wheel/native loader/fixture parity not tested |
| Child process environment | Explicit child env dictionary contains **PATH and NODE_PATH only**, without \`TZ\`; host process runner env similarly does not pin TZ | R25 \`usr/share/zoneinfo/UTC\` absent | Timezone determinism of child processes is **not proven** |
| Security boundary | A1 calls \`require_worker_launch\` before OCI spawn; A6 still raises \`A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED\` | R25 static filesystem not executable certification | Independent rootless OCI+gVisor confinement/escape assessment missing; unknown user code DENIED |

**No guest or Worker code was executed in R26.** Package provenance is not the same as permitted execution. The R25 final filesystem does not include TS/Wasm dependencies, original Worker byte payload or a production Worker entrypoint.

## 4. Fail-closed product and QA decision

- **PASS:** Eight exact original source blobs; fixed aware-datetime-to-UTC semantics; \`observed_at\` pass-through; source-monotonic timeout; recorded absence of \`usr/share/zoneinfo/UTC\` in actual R25 OCI static inventory; unchanged A6 hard DENY.
- **NOT ESTABLISHED:** deterministic behavior of any arbitrary guest/date library, ICU/IANA timezone equivalence, TLS/CA/NSS runtime validity, Node 18→24 behavior, Python/Node actual loader execution, TypeScript and Wasmtime loading, four-language fixture equivalence, gVisor/rootless host approval.
- **No change made:** No \`tzdata\` added, no distro source mutation, no Worker/OCl release, no amended signed index or Debian lock, **0 CVEs closed**, original **199 Critical/High findings REVIEW-OPEN**, no PR merge.

**Next proposed CERT-A19-R27:** Define an explicit **UTC/offset-only vs named-timezone** feature contract for approved developer fixtures. Select and justify timezone-data source/immutability **only if** the contract needs IANA names. Independently check that the fixed safe fixture host is authorized before any target-code execution, then compare Node18/24 timestamp and \`Intl\` edge behavior with named daylight-saving transitions. Preserve the A6 hard DENY for arbitrary guest code throughout. No production build/deployment without independent sandbox certification.

**Formal R26 verdict:** \`CERT_A19_R26_FIXED_CORE_UTC_NO_DIRECT_TZDB_CALLS__GUEST_TIMEZONE_AND_4_LANG_EXECUTION_UNPROVEN__A6_DENY_199_OPEN\`.
