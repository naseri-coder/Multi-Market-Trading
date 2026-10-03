# Roadmap

This roadmap describes engineering direction, not trading-performance promises.

## Current — v0.3.0 readiness

- Complete reviewed source convergence.
- Keep public source provenance and hash verification intact.
- Keep migrations, dependency locks, CI gates, and installation checks reproducible.
- Expand regression coverage around context, probability, risk, lifecycle, paper/shadow, and persistence behavior.
- Improve contributor onboarding and public maintenance documentation.
- Run an exact-SHA release-readiness pass before publishing v0.3.0.

## Next

- Broaden rule and context coverage while keeping interpretations explicit and testable.
- Improve explainability of why a setup passes, fails, or remains uncertain.
- Strengthen paper/shadow evaluation and replay tooling.
- Improve public developer documentation and issue-driven contribution paths.
- Continue security, dependency, and publication-safety review.

## Later

- Evaluate operational readiness only after the relevant safety, persistence, observability, and validation gates are satisfied.
- Consider additional integrations only when they can be isolated, tested, and maintained without weakening the existing safety model.

## Explicitly out of scope

- Profitability guarantees.
- Unvalidated live-trading claims.
- Treating discretionary source concepts as opaque numeric scores without documented engineering policy.
- Publishing private credentials, operational data, or copyrighted source material.
