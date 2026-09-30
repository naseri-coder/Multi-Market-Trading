from pathlib import Path


def test_phase8_module_has_no_database_telegram_or_signal_persistence_imports():
    root = Path("app/modules/shadow_replay")
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in root.glob("*.py")
    )
    forbidden = (
        "app.db",
        "sqlalchemy",
        "telegram",
        "signal_automation.repository",
        "signal_automation.service",
        "paper_runtime",
    )
    for token in forbidden:
        assert token not in text
