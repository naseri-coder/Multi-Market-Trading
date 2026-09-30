"""Missed opportunity reports only.
Does not influence decision making.
"""


class OpportunityAnalyzer:
    def analyze(self, candidates):
        return {
            "total_candidates": len(candidates),
            "reasons": {
                "low_confidence": 0,
                "weak_context": 0,
                "risk_too_high": 0,
                "pattern_missing": 0,
            },
            "analysis_only": True,
        }
