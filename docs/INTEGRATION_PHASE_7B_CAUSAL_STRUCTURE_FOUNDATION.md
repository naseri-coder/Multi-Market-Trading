# Integration Phase 7B — Causal Market Structure Foundation

## Source-grounded facts used

- BR-031: bull structure is HH/HL; bear structure is LH/LL.
- BR-010 / BR-011: exact inside/outside bar relations.
- Pages 11–12 support H2/L2 concepts, but full H1/H2/L1/L2 counting edge cases are not source-resolved.

## Engineering layer (explicitly NOT Brooks-authored thresholds)

EH-002 is implemented as configurable causal pivot confirmation:
- `left_bars`
- `right_bars`
- a swing is emitted only after right-side confirmation bars exist
- ties are marked ambiguous
- no future-bar information is used before confirmation

Default Phase 7B values are `left_bars=2`, `right_bars=2`. These are engineering defaults,
not claims from Brooks. They are versioned in `configuration_version`.

## EH-006 policy

H1/H2/L1/L2 is NOT fully implemented.
Inside bars, outside bars, equal highs and equal lows block counting.
A clean window may be called "eligible for future counting", but Phase 7B does not assign H1/H2/L1/L2.

## Runtime decision

The Phase 7B engine remains fail-closed and always returns NO_SIGNAL.

No migration.
No dependency changes.
PAPER remains disabled.
