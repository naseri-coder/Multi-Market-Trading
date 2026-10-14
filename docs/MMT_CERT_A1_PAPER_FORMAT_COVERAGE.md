# CERT-A1 extension — complete format capability registry, no execution grant

**Pre-existing baseline:** CERT-A1 was already delivered in PR #256 at
main SHA 9efd8095e9fb424641f9a16dea9cce15226230b3. The module
cert_a1_offline_candidate_review.py remains unchanged.

This follow-up adds a deterministic bounded cross-format inventory
in naseri_markets/cert_a1_paper_format_inventory.py. It distinguishes
artifact intake, PAPER market input, Core API wire preparation and
actual PAPER strategy execution for all currently registered suffixes.

## Review contract

Call review_paper_format_inventory with an exact tuple of
CandidateSubmission(filename, artifact_bytes, approved_sha256,
stage_evidence), an absolute local repository root,
MMT_NONPRODUCTION=1 and operator_ack=True.

- Re-review exact bytes via the existing CERT-A1 universal intake,
  A13 source/A6 audit, strict Pine parser and static PE/ELF checker.
- Permit at most one candidate per extension; refuse duplicate
  case-insensitive filenames and SHA reused across formats.
- Compare the entire suffix registry to an explicit capability matrix,
  failing closed if a new format appears without a contract.
- Return sorted rows, missing extensions, claim and review counts,
  plus a domain-separated fingerprint of this local audit metadata.
- require_all_formats=True refuses a missing format. Even a complete
  inventory has no software or execution certification authority.
- All source, sandbox, execution, broker, Telegram and distribution
  authority booleans are unconditionally FALSE.
- Neither original bytes nor account credentials are returned.

## Declared capability matrix

| Files | PAPER-relevant review only | Explicitly not certified |
| --- | --- | --- |
| CSV, Parquet | Claimed typed DATA-A1 CoreInput history | Exchange/PIT quality, strategy or order execution |
| PY, JS, TS, WASM | Claimed DATA-to-RUNTIME Core API frames | Worker execution, confinement or strategy results |
| Pine | Narrow closed-bar SMA rule and claimed oracle | General Pine conversion, actual TradingView/PnL parity |
| MQ4, MQ5, EX5 | Hash and claimed MetaTrader artifact identity | MetaEditor compile, DEMO terminal, EA results |
| DLL, EXE, SO | Static PE/ELF header reparse | Publisher authenticity, malware safety, native execution |
| ZIP | Canonical SDK structure review | Trusted signature or public distribution |
| JSON | General JSON syntax | Manifest registration or permissions |

**Every format has PAPER STRATEGY EXECUTION = FALSE.** Four Worker
languages can have framed requests and CSV/Parquet can have prepared
data inputs, but that is not a strategy evaluation or PAPER order.

## Threat and provenance boundaries

All stage evidence objects are plain caller-provided Python dataclasses.
Even if they contain the correct hash and expected status, they are not
signed by an independent producer or preserved in separately audited
custody. The inventory classifies them as matching untrusted claims.
A caller may control both artifact bytes and declared SHA256; that is
not external provenance or independent signer identity.

No real TradingView trace, broker-certified market history, MetaTrader
compiled object, gVisor isolation or disposable Windows/Linux native
sandbox was tested. No user-provided program is executed in CI.

## Acceptance

The dedicated workflow runs the new adversarial inventory tests and
existing CERT-A1, Pine, Native and A6 security contract tests. It checks
registered formats, canonical order, different artifact types, missing
evidence, duplicate inputs, forged stage authorizations, strict rejected
Pine syntax, incorrect hash, no process/network and production denials.

**Security verdict:** CERT_A1_PAPER_COVERAGE_INVENTORY_ONLY_ALL_EXECUTION_DENIED.

Further real-world certification needs independently custodied source
provenance, trusted signing/operator identities, true market-data
point-in-time source validation, latest receipt custody and approved,
independently isolated runtime observations. Only a separate explicit
authorization could ever consider a change to A6.
