"""Deterministic Brooks knowledge extractor.

This evaluator has no side effects and no dependency on AI, risk, quality, signal,
Telegram, database, or publication layers.
"""
from __future__ import annotations

from dataclasses import replace

from app.modules.brooks_core.advanced_context import assess_advanced_context
from app.modules.brooks_core.books_full_patterns import scan_full_brooks_patterns
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.context_classifier import assess_books_context
from app.modules.market_data.entities import MarketSnapshot

from .entities import (
    BrooksKnowledgeSnapshot,
    KnowledgeCategory,
    KnowledgeFinding,
    SessionAnchor,
)
from .rules import (
    candidate_findings,
    context_findings,
    detect_always_in_failure,
    detect_final_flag_failure,
    detect_nested_trading_range,
    detect_successful_breakout,
    observation_findings,
    opening_session_findings,
)


def _dedupe(findings: tuple[KnowledgeFinding, ...]) -> tuple[KnowledgeFinding, ...]:
    unique: dict[tuple[object, ...], KnowledgeFinding] = {}
    for item in findings:
        key = (
            item.rule_id,
            item.concept,
            item.category,
            item.state,
            item.bias,
            item.bar_index,
            item.probability_band,
            item.evidence,
        )
        unique.setdefault(key, item)
    return tuple(
        sorted(
            unique.values(),
            key=lambda x: (x.bar_index, x.category.value, x.rule_id, x.concept),
        )
    )


def _evidence_projection(
    findings: tuple[KnowledgeFinding, ...],
) -> tuple[KnowledgeFinding, ...]:
    projected: list[KnowledgeFinding] = []
    for item in findings:
        if item.category is KnowledgeCategory.EVIDENCE:
            projected.append(item)
            continue
        projected.append(
            replace(
                item,
                category=KnowledgeCategory.EVIDENCE,
                concept=f"Evidence: {item.concept}",
            )
        )
    return _dedupe(tuple(projected))


class BrooksKnowledgeEngine:
    """Pure, synchronous, replay-safe market-knowledge evaluator."""

    engine_version = "brooks-knowledge-v1"

    def __init__(self, *, policy: BrooksFullCorePolicy | None = None) -> None:
        policy = policy or BrooksFullCorePolicy()
        if policy.enable_trade_decisions:
            policy = replace(policy, enable_trade_decisions=False)
        self.policy = policy

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        *,
        session: SessionAnchor | None = None,
    ) -> BrooksKnowledgeSnapshot:
        context = assess_books_context(snapshot, policy=self.policy.context)
        advanced = assess_advanced_context(snapshot, policy=self.policy)
        scan = scan_full_brooks_patterns(snapshot, context, self.policy)

        findings: list[KnowledgeFinding] = list(
            context_findings(snapshot, context, advanced)
        )
        for observation in scan.observations:
            findings.extend(observation_findings(observation))
        for candidate in scan.candidates:
            findings.extend(candidate_findings(candidate, context, advanced))

        findings.extend(detect_successful_breakout(snapshot, context))
        findings.extend(detect_nested_trading_range(snapshot))
        findings.extend(detect_final_flag_failure(snapshot, self.policy))
        findings.extend(detect_always_in_failure(snapshot, self.policy))
        findings.extend(opening_session_findings(snapshot, self.policy, session))

        base = _dedupe(tuple(findings))
        evidence = _evidence_projection(base)

        def category(kind: KnowledgeCategory) -> tuple[KnowledgeFinding, ...]:
            return tuple(item for item in base if item.category is kind)

        return BrooksKnowledgeSnapshot(
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_hash,
            detected_structures=category(KnowledgeCategory.STRUCTURE),
            detected_context=category(KnowledgeCategory.CONTEXT),
            detected_trend=category(KnowledgeCategory.TREND),
            detected_range=category(KnowledgeCategory.RANGE),
            detected_channel=category(KnowledgeCategory.CHANNEL),
            detected_pressure=category(KnowledgeCategory.PRESSURE),
            detected_traps=category(KnowledgeCategory.TRAP),
            detected_entries=category(KnowledgeCategory.ENTRY),
            detected_failures=category(KnowledgeCategory.FAILURE),
            detected_probabilities=category(KnowledgeCategory.PROBABILITY),
            detected_evidence=evidence,
        )
