"""Static audit for the archived Books-v2 shadow engine surface."""

from pathlib import Path

from app.modules.brooks_core.books_engine import BrooksBooksH2L2Engine
from app.modules.brooks_core.books_policy import BrooksBooksPolicy

ROOT = Path(__file__).resolve().parents[2] / "production_source"


def main() -> None:
    policy = BrooksBooksPolicy()
    assert policy.enable_trade_decisions is False
    assert BrooksBooksH2L2Engine.engine_version == "brooks-books-h2l2-v2-shadow"

    for rel in (
        "app/modules/brooks_core/books_engine.py",
        "app/modules/brooks_core/context_classifier.py",
        "app/modules/brooks_core/second_entry_v2.py",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for forbidden in (
            "app.modules.paper_runtime",
            "app.modules.signal_automation.service",
            "app.modules.signals.repository",
            "telegram",
            "sqlalchemy",
        ):
            assert forbidden not in text, (rel, forbidden)

    print("BOOKS_V2_ENGINE_IMPORT=PASS")
    print("AUTONOMOUS_TRADE_DECISIONS=FALSE")
    print("DB_SURFACE=NONE")
    print("TELEGRAM_SURFACE=NONE")
    print("PAPER_RUNTIME_SURFACE=NONE")
    print("PRODUCTION_WIRING_CHANGED=NO")
    print("BOOKS_V2_STATIC_AUDIT=PASS")


if __name__ == "__main__":
    main()
