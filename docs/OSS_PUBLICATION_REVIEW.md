# OSS Publication Review

Status: public development snapshot. This document records publication-review boundaries; it is not legal advice and does not authorize production deployment or live trading.

## Frozen source boundary

The curated `production_source/SHA256SUMS` snapshot contains 348 hash-verified files. The frozen release identity is defined by the files listed in that manifest. A listed file must not be edited as ordinary documentation cleanup because doing so requires a new reviewed manifest and release identity.

Ancillary files under `production_source/` that are not listed in `SHA256SUMS` do not change the 348-file frozen identity when edited, but publication changes to them still require normal review and CI validation.

## Source-expression review

The implementation distinguishes source rules, source interpretations, and engineering policy.

The targeted review of the following source-oriented files has been completed for the current release-candidate lineage:

- `production_source/app/modules/brooks_core/second_entry.py`
- `production_source/app/modules/brooks_core_v3/knowledge/source_registry.py`
- `production_source/app/modules/brooks_core_v3/traders_equation/source.py`
- `production_source/app/modules/brooks_core/books_engine.py`
- `production_source/app/modules/brooks_core/books_full_engine.py`
- `production_source/app/modules/brooks_core/source_rules.py`
- `production_source/app/modules/brooks_core_v3/source_catalog.py`

No book scans, figures, tables, or long reproduced passages were identified in those files. The longer text blocks reviewed were implementation, provenance, or engineering explanations rather than source-text reproduction. No frozen-source edit was required by this review. Any later source change reopens this gate.

## Branding and affiliation

The public README states that the project is independent and is not affiliated with, sponsored by, or endorsed by Al Brooks or the publishers of the referenced books.

## Secrets, history, and operational data

The candidate uses placeholder values in `.env.example` and ignores common secret/data file classes. The tracked public tree is checked by publication CI.

The release-readiness review also checked the reachable repository history for credential-oriented indicators and reviewed GitHub-native security findings. At that review point, GitHub showed zero open Code Scanning alerts, zero open Secret Scanning alerts with no unresolved secrets, and zero open Dependabot vulnerability alerts.

These checks materially reduce credential and dependency-publication risk, but they are not a universal proof that arbitrary personally identifiable information could never exist in history. Any newly discovered privacy evidence reopens this gate.

## Release validation rule

Before an official tagged release, the exact commit being released must pass the publication-safety and main-branch security/CodeQL gates, the isolated Stage3B install verification, and the final release-artifact review.

Any commit after an exact-SHA validation changes the release candidate and therefore requires the affected exact-SHA gates to be rerun. Creating a tag, GitHub Release, or production deployment remains a separate explicitly authorized operation.
