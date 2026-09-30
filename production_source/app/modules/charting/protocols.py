from pathlib import Path
from typing import Protocol
from app.modules.market_data.entities import MarketSnapshot

class SignalChartRenderer(Protocol):
    def render(
        self,
        *,
        snapshot: MarketSnapshot,
        direction: str,
        entry_price: object,
        stop_loss: object,
        targets: tuple[object, ...],
        setup_type: str | None,
        output_path: Path,
        chart_evidence=None,
    ) -> Path: ...
