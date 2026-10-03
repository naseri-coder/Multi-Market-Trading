# Cold Start Qualitative Policy V1 — PRE-PRODUCTION

Status: offline validation only. Not wired into production publication.

## Eligibility
Fallback is eligible only when Historical Probability returns exactly `COLD_START_INSUFFICIENT_COMPATIBLE_HISTORY`. It never substitutes for a calibrated negative EV, cohort mismatch, cohort-unspecified state, AI rejection, Risk rejection, invalid geometry, structural invalidation, absolute Brooks veto, MAJOR evidence conflict, or any Final Gate failure other than `PROBABILITY_UNCALIBRATED`.

## Conservative qualitative gate
Use only existing V5/V6 evidence already produced by `score_candidate`: structure quality >= 75, context quality >= 75, entry quality >= 90, risk quality >= 85, and Brooks certainty >= 0.80. No new weighted score is introduced. Ordinary Final Gate minima are structure 60, context 60, risk 75; therefore the Cold Start thresholds are stricter and add entry/certainty requirements.

Policy version: `COLD_START_QUALITATIVE_POLICY_V1`.
Configuration tag: `coldq1-s75-c75-e90-r85-bc0.80-exit20`.
Future integrated candidate `configuration_version` must include this tag; Phase 4.2.41.84 does not alter production configuration.

## Exit condition
The fallback is disabled before evaluating the next candidate once there are 20 CLOSED native-compatible outcomes for the exact calibration cohort. One signal contributes at most one latest terminal outcome, and only `TARGET_HIT` or `STOP_HIT` counts. OPEN, merely published, expired, ambiguous, or otherwise non-binary outcomes do not count.

Compatibility is exact on engine_version, rule_set_version, configuration_version, exchange, market_type, and trade-management policy version. The number 20 is not fitted to the recovered cohort: it is the existing Historical Probability broad-pool minimum (`_MIN_BROAD=20`), larger than the exact/family minima of 8/12. It is a minimum handoff point to the existing Wilson-based statistical gate, not a claim that n=20 yields a narrow confidence interval. If the normal engine still reports insufficient compatible history after the global exit count is reached, the candidate is rejected; the qualitative fallback does not remain available.

## Persistence / separation
Every fallback-accepted signal must store `admission_gate=COLD_START_QUALITATIVE_GATE`, `cold_start_policy_version`, `cold_start_configuration_tag`, `statistically_calibrated_at_admission=false`, and the admission-time calibration status/counts in existing `signal_automation_metadata.analysis_metadata` JSONB. No schema migration is required for this minimum label.

Cold-start outcomes are native V5/V6 observations and may be intentionally used to bootstrap future Historical Probability only under the explicit cohort/counting rule above. Performance reporting must segment them from statistically calibrated-at-admission signals using the persisted label; they must never be silently mixed into a "calibrated admission win-rate" metric.

## Phase 4.2.41.84 sanity result
The precommitted threshold produced 8 PASS / 6 REJECT on the exact 14-candidate Risk-V6-survivor cohort (>50%). Per phase rules this is a deployment blocker, not a trigger for automatic retuning. Five of the eight passes sit exactly on the structure threshold (75), and one pass has a MODERATE measured-move conflict. Further holdout/policy review is required before any production activation.
