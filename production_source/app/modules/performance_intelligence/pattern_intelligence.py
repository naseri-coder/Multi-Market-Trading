"""Pattern performance analytics only.
No signal generation or rule mutation.
"""

from decimal import Decimal
from collections import defaultdict


class PatternIntelligence:
    def profile(self, signals):
        groups = defaultdict(list)
        for signal in signals:
            groups[signal.get("pattern", "UNKNOWN")].append(signal)
        result = {}
        for pattern, rows in groups.items():
            wins = sum(1 for row in rows if row.get("outcome") == "WIN")
            result[pattern] = {
                "sample_count": len(rows),
                "win_rate": Decimal(wins) / Decimal(len(rows)) if rows else Decimal(0),
                "analysis_only": True,
            }
        return result
