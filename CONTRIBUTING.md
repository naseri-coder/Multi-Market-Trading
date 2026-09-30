# Contributing

Thank you for your interest in the project.

## Development principles

Changes should preserve causal, closed-bar behavior and keep source-derived concepts separate from engineering policy. New numeric thresholds that are not explicitly part of a source rule should be identified as engineering policy.

Do not submit copyrighted book text, scans, figures, tables, screenshots, or other non-code source material. Short identifiers and independently written descriptions should be preferred over reproducing source prose.

## Security and privacy

Never include live credentials, `.env` files, private keys, database dumps, operational logs, administrator identifiers, realized trades, or private datasets in commits, issues, pull requests, or test fixtures.

## Pull requests

Keep changes focused. Explain the behavior being changed, the tests or checks performed, and whether the change affects trading semantics, persistence, migrations, or source provenance.

For source-manifest changes, update and verify the curated manifest as part of a separately reviewed release operation. Do not silently modify files under `production_source/` while continuing to claim the previous frozen manifest identity.
