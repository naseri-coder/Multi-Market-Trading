# Brooks Core v3 — Phase 1 Book-Alignment Audit

## Scope
Audit target: active `app/modules/brooks_core` + downstream evidence/scoring path.
Primary authority: Al Brooks trilogy only. Deterministic numeric cutoffs remain explicitly engineering policy.

Classification:
1. **ALIGNED** — source semantics are represented faithfully enough for deterministic OHLC use.
2. **INCOMPLETE** — source concept exists, but important context/behavior is missing.
3. **OUTDATED/MISALIGNED** — current implementation materially distorts the intended Brooks decision hierarchy.

## Rule audit
| Rule / area | Class | Finding | Phase-1 action |
|---|---:|---|---|
| BB-TRD-19 Trend Strength | 2 | Multi-factor, but channel strength and failed-countertrend behavior are not first-class | Refactor context features |
| BB-RNG-CTX Trend vs Range | 2 | Range logic is useful but fixed-window geometry dominates location | Refactor context weighting |
| BB-RNG-02 Breakout Follow-through | 2 | Fresh breakout candidate can be created from one strong bar | Require stronger follow-through context |
| BB-RNG-05 Failed Breakout | 2 | Core return-inside semantics exist; failure strength/context is thin | Add context-quality evidence |
| BB-RNG-05 Failed Failure | 2 | Correct sequence exists; second-entry reliability not used in ranking | Add higher-probability qualifier |
| BB-RNG-05 Breakout Pullback | 2 | 1–5 bar source window exists; resumption quality is underweighted | Refactor evidence/ranking |
| BB-RNG-17 H1/H2/L1/L2 | 2 | Bar counting is source-aligned, but only H2/L2 becomes a candidate | Expose H1/L1 conservatively |
| Second-entry core counting | 1 | Causal distinct-second-excursion interpretation is explicit and replay-safe | Keep |
| BB-REV-05 Wedge | 2 | Three pushes exist, but location/progression context is too permissive | Tighten third-push/context validation |
| BB-REV-07 Final Flag | 3 | Fixed 6-bar/35% geometry misses one-bar, ii/barbwire and micro-double variants | Replace rigid detector with flexible flag logic |
| BB-REV Double Top/Bottom | 2 | Swing tests exist; micro variants are absent | Add micro DT/DB interpretation |
| Measured Move | 2 | Not first-class; current execution uses generic R targets | Add magnet/evidence only; do not replace Risk Engine |
| BB-REV-15 Always In | 2 | Two-strong-bar default is useful but too rigid when a decisive breakout bar establishes context | Add causal single-breakout exception |
| Spike & Channel | 2 | Discussed in sources but not represented first-class | Add descriptive context evidence |
| Tight Channel / Micro Channel | 2 | Tight range exists; directional tight channel does not | Add directional context evidence |
| Opening Reversal | 2 | No session-aware crypto contract exists | Fail closed until an explicit session anchor is supplied |
| Higher Probability Filter | 2 | Reliability clues exist but are not a qualitative selection layer | Add source-grounded HIGHER/NORMAL/LOWER assessment |
| BB-RNG-26 Two Reasons | 1 | Candidate invariant requires two independent reasons | Keep; do not let it dominate weighted evidence |
| Evidence certainty | 3 | PASS/AMBIGUOUS are counted equally by rule count | Replace with Strong/Normal/Weak weighted evidence |
| Candidate final scoring | 3 | 60% AI + 40% Risk plus regime adjustment bypasses Brooks structure/context/entry hierarchy | Replace with Structure/Context/Entry/Risk quality |

## Non-goals / safety
- No new setup without a Brooks source concept.
- No calibrated probability is claimed from qualitative Brooks language.
- Measured moves remain contextual magnets, not universal targets.
- Opening reversal remains unavailable for 24/7 crypto without a defined session boundary.
- Existing Risk Engine and AI Council remain unchanged unless a direct contradiction is demonstrated.
- Legacy rule IDs are retained for replay compatibility; no deletion is planned in Phase 1.
