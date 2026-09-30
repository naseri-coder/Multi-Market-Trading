"""Source-aware Brooks evidence weighting.

Strong/Normal/Weak are engineering significance classes requested for ranking evidence.
They are not claimed as numeric probabilities authored by Al Brooks.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class RuleStrength(StrEnum):
    STRONG = "STRONG"
    NORMAL = "NORMAL"
    WEAK = "WEAK"


class QualityDimension(StrEnum):
    STRUCTURE = "STRUCTURE"
    CONTEXT = "CONTEXT"
    ENTRY = "ENTRY"


_STRENGTH_WEIGHT = {
    RuleStrength.STRONG: 3.0,
    RuleStrength.NORMAL: 2.0,
    RuleStrength.WEAK: 1.0,
}

@dataclass(frozen=True, slots=True)
class RuleWeightProfile:
    rule_id: str
    strength: RuleStrength
    dimension: QualityDimension
    rationale: str

    @property
    def weight(self) -> float:
        return _STRENGTH_WEIGHT[self.strength]

    @property
    def context_dependency(self) -> str:
        if self.dimension is QualityDimension.CONTEXT:
            return "CONTEXT_CRITICAL"
        if self.dimension is QualityDimension.STRUCTURE:
            return "CONTEXT_SENSITIVE"
        return "SETUP_AND_CONTEXT_DEPENDENT"

    @property
    def structure_importance(self) -> str:
        if self.dimension is QualityDimension.STRUCTURE:
            return "PRIMARY"
        if self.strength is RuleStrength.STRONG:
            return "SECONDARY"
        return "CONTEXTUAL"


_PROFILES = (
    RuleWeightProfile("BB-TRD-19-TREND-STRENGTH", RuleStrength.STRONG, QualityDimension.STRUCTURE, "multi-factor trend state"),
    RuleWeightProfile("BB-REV-15-ALWAYS-IN", RuleStrength.STRONG, QualityDimension.CONTEXT, "dominant side / trade direction context"),
    RuleWeightProfile("BB-RNG-02-BREAKOUT-FOLLOWTHROUGH", RuleStrength.STRONG, QualityDimension.CONTEXT, "breakout strength and follow-through"),
    RuleWeightProfile("BB-RNG-17-HL-BAR-COUNT", RuleStrength.STRONG, QualityDimension.ENTRY, "H1/H2/L1/L2 event semantics"),
    RuleWeightProfile("BB-RNG-05-FAILED-FAILURE", RuleStrength.STRONG, QualityDimension.ENTRY, "second failure / second signal"),
    RuleWeightProfile("BB-REV-03-MAJOR-TREND-REVERSAL", RuleStrength.STRONG, QualityDimension.STRUCTURE, "break then test reversal structure"),
    RuleWeightProfile("BB-TRD-TIGHT-CHANNEL", RuleStrength.STRONG, QualityDimension.CONTEXT, "tight channel implies strong trend and failed first countertrend breakout"),
    RuleWeightProfile("BB-TRD-SPIKE-CHANNEL", RuleStrength.STRONG, QualityDimension.CONTEXT, "spike plus pullback/resumption trend context"),
)

_PROFILES += (
    RuleWeightProfile("BB-RNG-05-BREAKOUT-PULLBACK", RuleStrength.NORMAL, QualityDimension.ENTRY, "with-trend breakout resumption"),
    RuleWeightProfile("BB-RNG-05-FAILED-BREAKOUT", RuleStrength.NORMAL, QualityDimension.ENTRY, "reversal after rejected breakout"),
    RuleWeightProfile("BB-RNG-21-BUY-LOW-SELL-HIGH", RuleStrength.NORMAL, QualityDimension.ENTRY, "trading-range location"),
    RuleWeightProfile("BB-RNG-22-TIGHT-RANGE", RuleStrength.NORMAL, QualityDimension.CONTEXT, "two-sided balance / whipsaw context"),
    RuleWeightProfile("BB-REV-05-WEDGE-THREE-PUSH", RuleStrength.NORMAL, QualityDimension.STRUCTURE, "three-push reversal structure"),
    RuleWeightProfile("BB-REV-05-MICRO-WEDGE", RuleStrength.NORMAL, QualityDimension.STRUCTURE, "micro three-push reversal structure"),
    RuleWeightProfile("BB-RNG-18-WEDGE-PULLBACK", RuleStrength.NORMAL, QualityDimension.ENTRY, "wedge pullback entry context"),
    RuleWeightProfile("BB-REV-07-FINAL-FLAG", RuleStrength.NORMAL, QualityDimension.ENTRY, "late flag reversal"),
    RuleWeightProfile("BB-REV-DOUBLE-TOP-BOTTOM", RuleStrength.NORMAL, QualityDimension.ENTRY, "test of prior extreme"),
    RuleWeightProfile("BB-REV-MICRO-DOUBLE-TOP-BOTTOM", RuleStrength.NORMAL, QualityDimension.ENTRY, "micro reversal/failure structure"),
    RuleWeightProfile("BB-TRD-MEASURED-MOVE", RuleStrength.NORMAL, QualityDimension.CONTEXT, "measured-move magnet, not standalone entry"),
    RuleWeightProfile("BB-TRD-OPENING-REVERSAL", RuleStrength.NORMAL, QualityDimension.CONTEXT, "session-open reversal; unavailable without session anchor"),
    RuleWeightProfile("BB-REV-04-CLIMACTIC-REVERSAL", RuleStrength.NORMAL, QualityDimension.STRUCTURE, "climax plus reversal"),
)

_PROFILES += (
    RuleWeightProfile("BB-RNG-26-TWO-REASONS", RuleStrength.WEAK, QualityDimension.CONTEXT, "meta-confluence rule; must not double-count directional edge"),
    RuleWeightProfile("BB-RNG-29-SIGNAL-BAR-STOP", RuleStrength.WEAK, QualityDimension.ENTRY, "execution geometry evidence"),
    RuleWeightProfile("BB-RNG-17-H2L2-TREND-CONTEXT", RuleStrength.WEAK, QualityDimension.CONTEXT, "legacy context alias retained for replay"),
    RuleWeightProfile("BB-RNG-CTX-TREND-VS-RANGE", RuleStrength.WEAK, QualityDimension.CONTEXT, "legacy context alias retained for replay"),
    RuleWeightProfile("BB-REV-03-REVERSAL-MATURITY", RuleStrength.WEAK, QualityDimension.CONTEXT, "legacy maturity proxy retained for replay"),
)

_PROFILES += (
    RuleWeightProfile("BB-TRD-04-CANDLE-PATTERNS", RuleStrength.WEAK, QualityDimension.ENTRY, "base candle-pattern observation"),
    RuleWeightProfile("BB-TRD-05-TWO-BAR-REVERSAL", RuleStrength.NORMAL, QualityDimension.ENTRY, "multi-bar reversal signal context"),
    RuleWeightProfile("BB-TRD-05-THREE-BAR-REVERSAL", RuleStrength.NORMAL, QualityDimension.ENTRY, "multi-bar reversal signal context"),
    RuleWeightProfile("BB-TRD-06-II-III", RuleStrength.NORMAL, QualityDimension.ENTRY, "ii/iii breakout-mode structure"),
    RuleWeightProfile("BB-TRD-06-IOI", RuleStrength.NORMAL, QualityDimension.ENTRY, "ioi breakout-mode structure"),
    RuleWeightProfile("BB-TRD-06-BREAKOUT-MODE", RuleStrength.NORMAL, QualityDimension.ENTRY, "direction requires breakout trigger"),
    RuleWeightProfile("BB-TRD-06-REVERSAL-BAR-FAILURE", RuleStrength.STRONG, QualityDimension.ENTRY, "failed reversal traps countertrend traders"),
    RuleWeightProfile("BB-TRD-06-SHAVED-BAR", RuleStrength.WEAK, QualityDimension.CONTEXT, "meaningful only in strong trend"),
    RuleWeightProfile("BB-TRD-06-EXHAUSTION-BAR", RuleStrength.NORMAL, QualityDimension.CONTEXT, "large trend bar can be climax/exhaustion"),
    RuleWeightProfile("BB-TRD-06-LEDGE", RuleStrength.WEAK, QualityDimension.CONTEXT, "small range with repeated equal extreme"),
    RuleWeightProfile("BB-TRD-07-OUTSIDE-BAR", RuleStrength.WEAK, QualityDimension.CONTEXT, "outside bars require context"),
    RuleWeightProfile("BB-RNG-06-GAPS", RuleStrength.NORMAL, QualityDimension.CONTEXT, "gap is breakout/strength context"),
    RuleWeightProfile("BB-RNG-12-DOUBLE-TOP-BEAR-FLAG", RuleStrength.STRONG, QualityDimension.ENTRY, "with-trend double-top continuation"),
    RuleWeightProfile("BB-RNG-12-DOUBLE-BOTTOM-BULL-FLAG", RuleStrength.STRONG, QualityDimension.ENTRY, "with-trend double-bottom continuation"),
    RuleWeightProfile("BB-RNG-13-TWENTY-GAP", RuleStrength.NORMAL, QualityDimension.ENTRY, "first MA touch after prolonged separation"),
    RuleWeightProfile("BB-RNG-14-FIRST-MA-GAP", RuleStrength.NORMAL, QualityDimension.ENTRY, "first gap-bar test of trend extreme"),
    RuleWeightProfile("BB-RNG-14-SECOND-MA-GAP", RuleStrength.STRONG, QualityDimension.ENTRY, "second attempt after first MA-gap reversal fails"),
)

_PROFILES += (
    RuleWeightProfile("BB-RNG-19-DUELING-LINES", RuleStrength.NORMAL, QualityDimension.CONTEXT, "visible support/resistance confluence at pullback end"),
    RuleWeightProfile("BB-RNG-20-HEAD-SHOULDERS-AS-RANGE", RuleStrength.WEAK, QualityDimension.CONTEXT, "alias of range/flag, not magic reversal"),
    RuleWeightProfile("BB-RNG-23-TRIANGLE", RuleStrength.NORMAL, QualityDimension.STRUCTURE, "five-leg breakout-mode trading range"),
    RuleWeightProfile("BB-REV-06-EXPANDING-TRIANGLE", RuleStrength.NORMAL, QualityDimension.STRUCTURE, "five-swing expanding three-push/MTR variant"),
    RuleWeightProfile("BB-REV-08-DOUBLE-BOTTOM-PULLBACK", RuleStrength.STRONG, QualityDimension.ENTRY, "reliable three-push breakout-pullback long"),
    RuleWeightProfile("BB-REV-08-DOUBLE-TOP-PULLBACK", RuleStrength.STRONG, QualityDimension.ENTRY, "reliable three-push breakout-pullback short"),
    RuleWeightProfile("BB-REV-09-FAILURES", RuleStrength.STRONG, QualityDimension.ENTRY, "failed setup traps traders and can reverse"),
    RuleWeightProfile("BB-TRD-23-SMALL-PULLBACK-TREND", RuleStrength.NORMAL, QualityDimension.CONTEXT, "persistent shallow pullback trend"),
    RuleWeightProfile("BB-TRD-23-TREND-FROM-OPEN", RuleStrength.WEAK, QualityDimension.CONTEXT, "session pattern unavailable without anchor"),
    RuleWeightProfile("BB-TRD-24-REVERSAL-DAY", RuleStrength.WEAK, QualityDimension.CONTEXT, "session pattern unavailable without anchor"),
    RuleWeightProfile("BB-TRD-25-TREND-RESUMPTION-DAY", RuleStrength.WEAK, QualityDimension.CONTEXT, "session pattern unavailable without anchor"),
    RuleWeightProfile("BB-TRD-26-STAIRS-BROAD-CHANNEL", RuleStrength.NORMAL, QualityDimension.STRUCTURE, "broad channel / stairs trend structure"),
    RuleWeightProfile("BB-TRD-26-SHRINKING-STAIRS", RuleStrength.NORMAL, QualityDimension.CONTEXT, "shrinking breakout extensions indicate waning trend momentum"),
    RuleWeightProfile("BB-REV-19-OPENING-REVERSAL", RuleStrength.WEAK, QualityDimension.CONTEXT, "session opening reversal requires anchor"),
    RuleWeightProfile("BB-REV-20-GAP-OPENING", RuleStrength.WEAK, QualityDimension.CONTEXT, "session gap opening requires anchor"),
)

_PROFILES += (
    RuleWeightProfile("BB-TRD-16-MICRO-CHANNEL", RuleStrength.STRONG, QualityDimension.CONTEXT, "micro channel is extreme tight-trend strength"),
    RuleWeightProfile("BB-TRD-22-TRENDING-RANGE", RuleStrength.NORMAL, QualityDimension.STRUCTURE, "sloping two-sided trading range structure"),
    RuleWeightProfile("BB-REV-10-HUGE-VOLUME-DAILY", RuleStrength.WEAK, QualityDimension.CONTEXT, "daily volume reversal is context, not standalone entry"),
)

_PROFILES += (
    RuleWeightProfile("BB-TRD-SPIKE", RuleStrength.STRONG, QualityDimension.CONTEXT, "strong breakout/spike phase context"),
    RuleWeightProfile("BB-TRD-CHANNEL", RuleStrength.NORMAL, QualityDimension.STRUCTURE, "trend-channel structure from repeated causal swings"),
    RuleWeightProfile("BB-REV-05-PARABOLIC-WEDGE", RuleStrength.STRONG, QualityDimension.STRUCTURE, "accelerating three-push climactic wedge"),
    RuleWeightProfile("BB-REV-09-MEASURED-MOVE-FAILURE", RuleStrength.NORMAL, QualityDimension.CONTEXT, "failure to reach a measured-move magnet"),
    RuleWeightProfile("BB-REV-09-MINOR-REVERSAL", RuleStrength.NORMAL, QualityDimension.STRUCTURE, "minor countertrend reversal without confirmed trend flip"),
    RuleWeightProfile("BB-RNG-14-GAP-BAR", RuleStrength.NORMAL, QualityDimension.CONTEXT, "moving-average gap bar; meaning depends on trend/range context"),
    RuleWeightProfile("BB-TRD-TREND-RESUMPTION", RuleStrength.STRONG, QualityDimension.ENTRY, "with-trend resumption after a pullback or failed reversal"),
)

_PROFILE_BY_ID = {item.rule_id: item for item in _PROFILES}

@dataclass(frozen=True, slots=True)
class WeightedEvidenceSummary:
    structure_quality: float
    context_quality: float
    entry_quality: float
    brooks_certainty: float
    weighted_pass: float
    weighted_possible: float
    unclassified_rule_ids: tuple[str, ...]


def rule_profile(rule_id: str) -> RuleWeightProfile | None:
    return _PROFILE_BY_ID.get(rule_id)


def _status_credit(status: str) -> float | None:
    normalized = str(status).upper()
    if normalized == "PASS":
        return 1.0
    if normalized == "AMBIGUOUS":
        return 0.5
    if normalized == "FAIL":
        return 0.0
    if normalized == "NOT_APPLICABLE":
        return None
    return 0.0


def summarize_evidence(evidence: Iterable[object]) -> WeightedEvidenceSummary:
    totals = {d: [0.0, 0.0] for d in QualityDimension}
    unclassified: set[str] = set()
    weighted_pass = 0.0
    weighted_possible = 0.0
    for item in evidence:
        rule_id = str(getattr(item, "rule_id", "") or "")
        profile = rule_profile(rule_id)
        if profile is None:
            if rule_id:
                unclassified.add(rule_id)
            continue
        credit = _status_credit(str(getattr(item, "status", "")))
        if credit is None:
            continue
        weight = profile.weight
        earned = weight * credit
        totals[profile.dimension][0] += earned
        totals[profile.dimension][1] += weight
        weighted_pass += earned
        weighted_possible += weight

    def quality(dimension: QualityDimension) -> float:
        earned, possible = totals[dimension]
        if possible <= 0:
            return 0.0
        return round((earned / possible) * 100.0, 2)

    certainty = 0.0 if weighted_possible <= 0 else weighted_pass / weighted_possible
    return WeightedEvidenceSummary(
        structure_quality=quality(QualityDimension.STRUCTURE),
        context_quality=quality(QualityDimension.CONTEXT),
        entry_quality=quality(QualityDimension.ENTRY),
        brooks_certainty=round(certainty, 4),
        weighted_pass=round(weighted_pass, 4),
        weighted_possible=round(weighted_possible, 4),
        unclassified_rule_ids=tuple(sorted(unclassified)),
    )


def all_rule_profiles() -> tuple[RuleWeightProfile, ...]:
    return _PROFILES


@dataclass(frozen=True, slots=True)
class RuleHistoricalReliability:
    rule_id: str
    sample_size: int
    wins: int
    losses: int
    reliability: float | None
    failure_probability: float | None
    historical_importance: int


@dataclass(frozen=True, slots=True)
class EvidenceConflict:
    rule_id: str
    reason: str
    severity: str
    weight: float
    dimension: QualityDimension


def _evidence_data(item: object) -> dict[str, str]:
    raw = getattr(item, "evidence", ()) or ()
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    result: dict[str, str] = {}
    for pair in raw:
        if isinstance(pair, (tuple, list)) and len(pair) >= 2:
            result[str(pair[0])] = str(pair[1])
    return result


def select_candidate_evidence(candidate: object) -> tuple[object, ...]:
    setup_type = str(getattr(candidate, "setup_type", "") or "")
    direction = str(getattr(candidate, "direction", "") or "").upper()
    selected: list[object] = []
    for item in tuple(getattr(candidate, "rule_evidence", ()) or ()):
        data = _evidence_data(item)
        evidence_setup = str(data.get("setup_type", ""))
        evidence_direction = str(data.get("direction", "")).upper()
        role = str(data.get("role", "")).upper()
        pattern_id = str(data.get("pattern_id", ""))
        if evidence_setup:
            if evidence_setup == setup_type and (
                not evidence_direction or evidence_direction == direction
            ):
                selected.append(item)
            continue
        if pattern_id and role not in {
            "CONTEXT", "FAILURE_CONTEXT", "NOT_APPLICABLE_SESSION_PATTERN"
        }:
            continue
        selected.append(item)
    return tuple(selected)


def _candidate_family(candidate: object) -> str:
    setup = str(getattr(candidate, "setup_type", "") or "").upper()
    for suffix in ("_LONG", "_SHORT"):
        if setup.endswith(suffix):
            setup = setup[:-len(suffix)]
    return setup


def detect_evidence_conflicts(candidate: object) -> tuple[EvidenceConflict, ...]:
    direction = str(getattr(candidate, "direction", "") or "").upper()
    family = _candidate_family(candidate)
    reversal_like = any(token in family for token in (
        "REVERSAL", "FAILED_BREAKOUT", "WEDGE", "FINAL_FLAG",
        "DOUBLE_TOP", "DOUBLE_BOTTOM", "EXPANDING_TRIANGLE", "MICRO_WEDGE",
    ))
    conflicts: list[EvidenceConflict] = []
    for item in select_candidate_evidence(candidate):
        data = _evidence_data(item)
        rule_id = str(getattr(item, "rule_id", "") or "")
        profile = rule_profile(rule_id)
        if profile is None:
            continue
        always_in = str(data.get("always_in", "")).upper()
        regime = str(data.get("regime", data.get("context", ""))).upper()
        tight = str(data.get("tight_channel", "")).upper()
        spike = str(data.get("spike_channel", "")).upper()
        measured = str(data.get("direction", "")).upper() if rule_id == "BB-TRD-MEASURED-MOVE" else ""
        reason = None
        severity = "MODERATE"
        if always_in in {"LONG", "SHORT"} and always_in != direction:
            reason = "candidate opposes resolved Always-In direction"
            severity = "MODERATE" if reversal_like else "MAJOR"
        elif regime == "BULL_TREND" and direction == "SHORT":
            reason = "candidate opposes bull-trend regime"
            severity = "MODERATE" if reversal_like else "MAJOR"
        elif regime == "BEAR_TREND" and direction == "LONG":
            reason = "candidate opposes bear-trend regime"
            severity = "MODERATE" if reversal_like else "MAJOR"
        elif tight in {"LONG", "SHORT"} and tight != direction:
            reason = "candidate opposes tight-channel direction"
            severity = "MAJOR"
        elif spike in {"LONG", "SHORT"} and spike != direction:
            reason = "candidate opposes spike-and-channel direction"
        elif measured in {"LONG", "SHORT"} and measured != direction:
            reason = "candidate opposes active measured-move magnet"
        if reason:
            conflicts.append(EvidenceConflict(
                rule_id=rule_id,
                reason=reason,
                severity=severity,
                weight=profile.weight,
                dimension=profile.dimension,
            ))
    unique = {(x.rule_id, x.reason): x for x in conflicts}
    return tuple(unique.values())


@dataclass(frozen=True, slots=True)
class CandidateEvidenceSummary:
    structure_quality: float
    context_quality: float
    entry_quality: float
    brooks_certainty: float
    selected_rule_ids: tuple[str, ...]
    conflicts: tuple[EvidenceConflict, ...]
    conflict_penalty: float
    unclassified_rule_ids: tuple[str, ...]


def _dedupe_candidate_evidence(candidate: object) -> tuple[object, ...]:
    chosen: dict[str, object] = {}
    for item in select_candidate_evidence(candidate):
        rule_id = str(getattr(item, "rule_id", "") or "")
        if not rule_id:
            continue
        data = _evidence_data(item)
        existing = chosen.get(rule_id)
        if existing is None:
            chosen[rule_id] = item
            continue
        current_specific = bool(data.get("setup_type"))
        existing_specific = bool(_evidence_data(existing).get("setup_type"))
        if current_specific and not existing_specific:
            chosen[rule_id] = item
    return tuple(chosen.values())


def summarize_candidate_evidence(candidate: object) -> CandidateEvidenceSummary:
    evidence = _dedupe_candidate_evidence(candidate)
    base = summarize_evidence(evidence)
    conflicts = detect_evidence_conflicts(candidate)
    possible = {dimension: 0.0 for dimension in QualityDimension}
    for item in evidence:
        profile = rule_profile(str(getattr(item, "rule_id", "") or ""))
        if profile is None:
            continue
        credit = _status_credit(str(getattr(item, "status", "")))
        if credit is not None:
            possible[profile.dimension] += profile.weight

    penalties = {dimension: 0.0 for dimension in QualityDimension}
    for conflict in conflicts:
        multiplier = 1.0 if conflict.severity == "MAJOR" else 0.5
        penalties[conflict.dimension] += conflict.weight * multiplier

    def adjusted(raw: float, dimension: QualityDimension) -> float:
        denominator = possible[dimension]
        if denominator <= 0:
            return raw
        reduction = min(100.0, penalties[dimension] / denominator * 100.0)
        return round(max(0.0, raw - reduction), 2)

    structure = adjusted(base.structure_quality, QualityDimension.STRUCTURE)
    context = adjusted(base.context_quality, QualityDimension.CONTEXT)
    entry = adjusted(base.entry_quality, QualityDimension.ENTRY)
    conflict_penalty = sum(penalties.values())
    certainty = round((structure + context + entry) / 300.0, 4)
    return CandidateEvidenceSummary(
        structure_quality=structure,
        context_quality=context,
        entry_quality=entry,
        brooks_certainty=certainty,
        selected_rule_ids=tuple(sorted(
            str(getattr(item, "rule_id", "") or "") for item in evidence
        )),
        conflicts=conflicts,
        conflict_penalty=round(conflict_penalty, 4),
        unclassified_rule_ids=base.unclassified_rule_ids,
    )
