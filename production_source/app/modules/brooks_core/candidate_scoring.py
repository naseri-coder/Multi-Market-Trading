"""Brooks-centric candidate quality decomposition.

The final_score is descriptive only. Trade approval belongs to the hard Final Gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from app.modules.brooks_core.evidence_weighting import (
    EvidenceConflict,
    summarize_candidate_evidence,
)


@dataclass(frozen=True, slots=True)
class CandidateQualityScore:
    structure_quality: float
    context_quality: float
    entry_quality: float
    risk_quality: float
    final_score: float
    brooks_certainty: float
    unclassified_rule_ids: tuple[str, ...]
    conflicts: tuple[EvidenceConflict, ...] = ()


def _clamp(value: float) -> float:
    return min(max(float(value), 0.0), 100.0)


def _mean_available(*values: float | None) -> float:
    selected = [float(item) for item in values if item is not None]
    return round(sum(selected) / len(selected), 2) if selected else 0.0

def score_candidate(
    candidate: object,
    *,
    risk_score: float,
    market_context: object | None = None,
) -> CandidateQualityScore:
    summary = summarize_candidate_evidence(candidate)
    risk_quality = round(_clamp(risk_score), 2)

    structure_context = None
    directional_context = None
    htf_context = None
    if market_context is not None:
        structure_context = _clamp(
            float(getattr(market_context, "swing_quality", 0.0)) * 100.0
        )
        direction = str(getattr(candidate, "direction", "") or "")
        alignment = getattr(market_context, "direction_alignment", None)
        if callable(alignment):
            directional_context = _clamp(float(alignment(direction)) * 100.0)
        # BROOKS-GAP-070: HTF evidence is candidate-relative.  Legacy
        # higher_timeframe_agreement is a current-vs-HTF diagnostic only and must
        # never give the opposite-direction candidate a positive HTF score.
        htf_alignment = getattr(market_context, "candidate_htf_alignment", None)
        if callable(htf_alignment) and direction in {"LONG", "SHORT"}:
            htf_state = htf_alignment(direction).state
            if htf_state == "ALIGNED_WITH_CANDIDATE":
                htf_context = 100.0
            elif htf_state == "OPPOSED_TO_CANDIDATE":
                htf_context = 0.0
            else:
                htf_context = None

    structure_quality = _mean_available(
        summary.structure_quality if summary.structure_quality > 0 else None,
        structure_context,
    )
    context_quality = _mean_available(
        summary.context_quality if summary.context_quality > 0 else None,
        directional_context,
        htf_context,
    )
    entry_quality = summary.entry_quality

    dimensions = (
        structure_quality,
        context_quality,
        entry_quality,
        risk_quality,
    )
    final_score = round(sum(dimensions) / len(dimensions), 2)
    return CandidateQualityScore(
        structure_quality=structure_quality,
        context_quality=context_quality,
        entry_quality=entry_quality,
        risk_quality=risk_quality,
        final_score=final_score,
        brooks_certainty=summary.brooks_certainty,
        unclassified_rule_ids=summary.unclassified_rule_ids,
        conflicts=summary.conflicts,
    )
