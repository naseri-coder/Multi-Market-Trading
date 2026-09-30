# OSS Publication Review

Status: public development snapshot. This document records publication-review boundaries; it is not legal advice and does not authorize production deployment or live trading.

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

The public README states that the project is independent and is not affiliated with, sponsored by, or endorsed by Al Brooks or the publishers of the referenced books.

## Secrets and operational data

The current candidate uses placeholder values in `.env.example` and ignores common secret/data file classes. The tracked public tree is checked by publication CI. Complete reachable-history review, GitHub-native secret scanning, and release-artifact review remain separate security gates.

## Remaining gates

The repository is public and uses Apache License 2.0 for project-owned code. Before an official tagged release, complete the targeted source-expression review, reachable-history/privacy review, GitHub-native security checks, public CI verification, and release-artifact review.
