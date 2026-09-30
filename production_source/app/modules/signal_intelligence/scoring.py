from __future__ import annotations


class SignalScoringEngine:
    """
    Adaptive signal scoring engine.

    Combines:
    - AI Council confidence
    - Risk Engine validation
    - Market regime adjustment
    """

    def calculate(
        self,
        ai_score: float,
        risk_score: float,
        market_regime: str,
    ) -> float:
        base_score = (
            (ai_score * 0.6)
            +
            (risk_score * 0.4)
        )

        adjustment = self._regime_adjustment(
            market_regime
        )

        final_score = base_score + adjustment

        return round(
            min(max(final_score, 0), 100),
            2,
        )

    def _regime_adjustment(
        self,
        market_regime: str,
    ) -> float:

        adjustments = {
            "TREND": 5.0,
            "LOW_VOLATILITY": 2.0,
            "RANGE": -5.0,
            "HIGH_VOLATILITY": -10.0,
            "UNKNOWN": 0.0,
        }

        return adjustments.get(
            market_regime,
            0.0,
        )

    def grade(
        self,
        score: float,
    ) -> str:
        if score >= 95:
            return "A+"

        if score >= 85:
            return "A"

        if score >= 75:
            return "B"

        if score >= 65:
            return "C"

        return "D"
