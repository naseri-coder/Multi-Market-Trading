from app.db.base import Base
from app.modules.paper_runtime.models import SignalDelivery


def test_signal_delivery_model_registered() -> None:
    assert SignalDelivery.__tablename__ == "signal_deliveries"
    assert "signal_deliveries" in Base.metadata.tables
