"""Failure classification reports.
This module observes outcomes only.
"""

from collections import Counter


class FailureAnalyzer:
    CATEGORIES = (
        "wrong_context",
        "weak_pattern",
        "poor_location",
        "late_entry",
        "failed_breakout",
        "risk_issue",
        "market_regime_mismatch",
    )

    def analyze(self, signals):
        failures = [s for s in signals if s.get("outcome") == "LOSS"]
        return {
            "count": len(failures),
            "categories": Counter(
                s.get("failure_category", "unknown") for s in failures
            ),
            "analysis_only": True,
        }
