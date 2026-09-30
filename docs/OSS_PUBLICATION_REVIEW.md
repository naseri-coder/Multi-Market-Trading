# OSS Publication Review

Status: pre-publication hardening. This document records review boundaries; it is not legal advice and does not itself authorize publication or production deployment.

## Frozen source boundary

The curated `production_source/SHA256SUMS` snapshot contains 348 hash-verified files. Files inside that snapshot must not be edited as ordinary documentation cleanup because doing so would invalidate the frozen release identity. Source sanitization requires a new reviewed manifest and release identity.

## Source-expression review

The implementation distinguishes source rules, source interpretations, and engineering policy. The current review has not identified book scans, figures, tables, or long reproduced passages in the inspected core files.

The following files require targeted review before a public release because they contain unusually detailed source metadata or source-oriented explanatory prose:

- `production_source/app/modules/brooks_core/second_entry.py`
- `production_source/app/modules/brooks_core_v3/knowledge/source_registry.py`
- `production_source/app/modules/brooks_core_v3/traders_equation/source.py`
- `production_source/app/modules/brooks_core/books_engine.py`
- `production_source/app/modules/brooks_core/books_full_engine.py`
- `production_source/app/modules/brooks_core/source_rules.py`
- `production_source/app/modules/brooks_core_v3/source_catalog.py`

The review goal is to keep independently implemented algorithms and necessary identifiers while minimizing source-specific prose and unnecessary page-by-page mappings in a public distribution.

## Branding and affiliation

Before public launch, the README should clearly state that the project is independent and is not affiliated with or endorsed by Al Brooks or the publishers of the referenced books.

## Secrets and operational data

The current candidate uses placeholder values in `.env.example` and ignores common secret/data file classes. A final publication gate should still inspect the complete reachable Git history and release tree for credentials, private operational identifiers, dumps, logs, keys, and private datasets.

## Remaining gates

The repository owner selected Apache License 2.0 for the project. A public release still requires completion of the targeted source-expression review, a final secret/history scan, verification of public-compatible CI, and an owner decision to change repository visibility.
