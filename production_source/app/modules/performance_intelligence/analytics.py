"""Analytics calculations for Performance Intelligence.

No trading decisions are produced here.
"""

from decimal import Decimal
from collections.abc import Iterable


class PerformanceAnalytics:
    def summarize(self, results: Iterable[dict]) -> dict:
        rows = list(results)
        total = len(rows)
        wins = sum(1 for r in rows if r.get("outcome") == "WIN")
        losses = sum(1 for r in rows if r.get("outcome") == "LOSS")
        return {
            "total_signals": total,
            "win_rate": Decimal(wins) / Decimal(total) if total else Decimal(0),
            "loss_rate": Decimal(losses) / Decimal(total) if total else Decimal(0),
            "mode": "report_only",
        }

    def pattern_profile(self, rows: Iterable[dict]) -> dict:
        items = list(rows)
        return {
            "sample_count": len(items),
            "win_rate": self.summarize(items)["win_rate"],
        }
