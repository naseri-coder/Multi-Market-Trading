# CERT-A1 — cross-format offline certification evidence reconciliation

**Verdict: NONPRODUCTION REVIEW ONLY — NO artifact execution certification.**

The first five requested stages (DATA-A1, RUNTIME-A1, MT-A1,
PINE-A1, NATIVE-A1) have separate, intentionally inert test contracts.
The repository also already provides Stage-14 Ed25519 SDK package
signatures in naseri_markets/core_certification_v1.py; CERT-A1
does not reimplement or supersede detached signature verification.

CERT-A1 consolidates this state into a **deny-by-default review report**,
without converting any offline evidence into installation, binary loading,
Worker launch, PAPER trade, live trade, broker permission or Telegram
sending authorization.

## Implementation: candidate audit, not installer

naseri_markets/cert_a1_offline_candidate_review.py exposes
review_candidate(repo_root, filename, artifact_bytes,
expected_sha256=..., stage_evidence=..., operator_ack=True).

It enforces:

- MMT_NONPRODUCTION=1, MMT_PRODUCTION not equal 1, and explicit
  operator acknowledgement.
- Exact source-byte SHA256, lowercase 64-hex, safe filename and bounded
  input through the existing universal artifact intake.
- Read-only A13 source-contract scan, including presence of A6
  unconditional denial in the two A1 dispatch choke points.
- Every universal-intake permission field must remain FALSE.
- PE DLL/EXE and ELF SO files must independently pass NATIVE-A1
  structural reinspection; a magic byte check alone is insufficient.
- Pine indicators must pass the exact restricted Pine v5/v6 closed-bar
  SMA-cross parser; arbitrary Pine code is rejected.
- Optional operator-provided stage review objects must have the
  right exact class, expected artifact hash, declared file type or
  runtime language, expected review-only status and no true approval
  or independent provenance fields.
- No raw candidate bytes or keys are stored in the resulting report.
  The report includes a domain-separated SHA256 fingerprint of
  normalized structural review metadata; this is not a signature,
  immutable ledger, timestamp or external checkpoint.

Stage review support:

| Candidate extension | CERT-A1 treatment |
| --- | --- |
| PY / JS / TS / WASM | universal intake and optional matching DATA→RUNTIME-A1 PAPER wire review; frames were prepared, not dispatched |
| CSV / Parquet | universal intake and optional matching DATA-A1 row/typed-input review; does not re-decode history from a claimed report |
| MQ4 / MQ5 / EX5 | basic intake and optional matching MT-A1 preflight report; no MetaEditor/terminal/source authenticity |
| Pine | strict static v5/v6 SMA subset plus optional match to offline operator-provided oracle trace; no genuine TradingView evidence |
| DLL / EXE / SO | independently reparse supplied bytes under NATIVE-A1, never native-load |
| ZIP | valid canonical SDK intake, optional Stage-14 review-only report; external signer trust still required |
| JSON | exact generic JSON structure only, no claim-based upgrade |

A dataclass can be forged by a caller, including a matching artifact hash.
It therefore must not be treated as proof of provenance or independent
certification. For any stage review supplied from elsewhere, CERT-A1
confirms only that it *claims* to cover the same bytes and declares
no permissions. Replaying a report is not authenticated because no
independent signed custody and freshness authority is in scope.

## Output and hard blockers

Every result has status
CERT_A1_OFFLINE_REVIEW_ONLY_EXECUTION_BLOCKED and explicit FALSE for:

- independent source/review provenance
- verified native host or sandbox isolation
- actual TradingView parity or absence of native malware
- native/Worker execution, quarantine release
- PAPER strategy execution and order sending
- broker, Telegram, public distribution and production recovery

Six external blockers always remain: independently custodied source
provenance; independently verified reviewer/signer identity; genuine
host confinement evidence; reproducible full dependency/image provenance;
trusted monotonic time and latest checkpoint; A6 unconditional launch
denial. Stage evidence is separately labeled MISSING or
MATCHED_BUT_UNATTESTED, never promoted to independent proof.

**Do not use CERT-A1 as a deployment gate whose successful return permits
anything.** A future real certification stage needs separately governed
publisher trust, source-security review, signed off-host provenance,
constrained binary execution on an independently designated disposable
host, a proven no-secrets/no-network sandbox, precise Core API and
rollback/restart tests, and explicit authorization to revise A6.
At present the Worker remains categorically denied.

## CI acceptance

The mock-only GitHub workflow runs CERT-A1 plus existing tests for
universal intake, A13/A6 hard stop, native file header preflight,
strict Pine parity and core SDK signature contract.
It tests valid structurally plausible synthetic PE/ELF byte buffers,
a narrow Pine sample, operator-provided and forged stage reports,
cross-language/format mismatch, bad hashes, unsafe filenames,
malformed archives, production-mode refusal and A6 source mutation.

No external market-provider record, MetaTrader terminal, TradingView
trace, actual third-party DLL/SO/EXE, native loader, Docker Worker,
broker, live PostgreSQL or Telegram destination is touched or
attested by this stage.

**Final classification: CERT_A1_RESEARCH_REVIEW_READY_RUNTIME_AND_RELEASE_NOT_CERTIFIED.**
