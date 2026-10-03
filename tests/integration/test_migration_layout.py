"""Static migration-chain checks that do not require a database server."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REVISION = PROJECT_ROOT / "migrations" / "versions" / "20260901_0001_create_core_models.py"
BROADCAST_REVISION = (
    PROJECT_ROOT / "migrations" / "versions" / "20260901_0002_create_broadcast_models.py"
)
FORWARD_REVISION = (
    PROJECT_ROOT / "migrations" / "versions" / "20260901_0003_add_forward_broadcast.py"
)
SUPPORT_REVISION = (
    PROJECT_ROOT / "migrations" / "versions" / "20260901_0004_create_support_ticket_models.py"
)
SIGNAL_REVISION = (
    PROJECT_ROOT
    / "migrations"
    / "versions"
    / "20260901_0005_create_signal_database_architecture.py"
)
SIGNAL_SERVICE_REVISION = (
    PROJECT_ROOT
    / "migrations"
    / "versions"
    / "20260901_0006_relax_signal_stop_loss_constraint.py"
)
FAVORITES_REVISION = (
    PROJECT_ROOT
    / "migrations"
    / "versions"
    / "20260901_0007_create_user_favorites.py"
)
NOTIFICATION_SETTINGS_REVISION = (
    PROJECT_ROOT
    / "migrations"
    / "versions"
    / "20260902_0008_create_user_notification_settings.py"
)
SUBSCRIPTIONS_REVISION = (
    PROJECT_ROOT
    / "migrations"
    / "versions"
    / "20260902_0009_create_subscription_architecture.py"
)
PAYMENTS_REVISION = (
    PROJECT_ROOT
    / "migrations"
    / "versions"
    / "20260902_0010_create_payment_architecture.py"
)
REFERRALS_REVISION = (
    PROJECT_ROOT
    / "migrations"
    / "versions"
    / "20260902_0011_create_referral_system.py"
)


def test_alembic_environment_and_initial_revision_exist() -> None:
    assert (PROJECT_ROOT / "alembic.ini").is_file()
    assert (PROJECT_ROOT / "migrations" / "env.py").is_file()
    assert REVISION.is_file()
    assert BROADCAST_REVISION.is_file()
    assert FORWARD_REVISION.is_file()
    assert SUPPORT_REVISION.is_file()
    assert SIGNAL_REVISION.is_file()
    assert SIGNAL_SERVICE_REVISION.is_file()
    assert FAVORITES_REVISION.is_file()
    assert NOTIFICATION_SETTINGS_REVISION.is_file()
    assert SUBSCRIPTIONS_REVISION.is_file()
    assert PAYMENTS_REVISION.is_file()
    assert REFERRALS_REVISION.is_file()


def test_initial_revision_is_valid_python_with_one_base_revision() -> None:
    source = REVISION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = ast.literal_eval(node.value)
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            assignments[node.targets[0].id] = ast.literal_eval(node.value)

    assert assignments["revision"] == "20260901_0001"
    assert assignments["down_revision"] is None


def test_initial_revision_creates_only_phase_three_tables() -> None:
    source = REVISION.read_text(encoding="utf-8")

    assert source.count("op.create_table(") == 4
    for table_name in ("users", "admins", "channels", "bot_settings"):
        assert f'        "{table_name}",' in source


def test_broadcast_revision_extends_initial_revision_with_two_tables() -> None:
    source = BROADCAST_REVISION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = ast.literal_eval(node.value)

    assert assignments["revision"] == "20260901_0002"
    assert assignments["down_revision"] == "20260901_0001"
    assert source.count("op.create_table(") == 2
    assert '        "broadcasts",' in source
    assert '        "broadcast_recipients",' in source


def test_forward_revision_extends_broadcast_revision_without_new_tables() -> None:
    source = FORWARD_REVISION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = ast.literal_eval(node.value)

    assert assignments["revision"] == "20260901_0003"
    assert assignments["down_revision"] == "20260901_0002"
    assert "op.create_table(" not in source
    assert '"source_chat_id"' in source
    assert '"source_message_id"' in source


def test_support_revision_extends_forward_revision_with_two_tables() -> None:
    source = SUPPORT_REVISION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = ast.literal_eval(node.value)

    assert assignments["revision"] == "20260901_0004"
    assert assignments["down_revision"] == "20260901_0003"
    assert source.count("op.create_table(") == 2
    assert '        "support_tickets",' in source
    assert '        "support_messages",' in source


def test_signal_revision_extends_support_revision_with_three_tables() -> None:
    source = SIGNAL_REVISION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = ast.literal_eval(node.value)

    assert assignments["revision"] == "20260901_0005"
    assert assignments["down_revision"] == "20260901_0004"
    assert source.count("op.create_table(") == 3
    assert '        "signals",' in source
    assert '        "signal_targets",' in source
    assert '        "signal_events",' in source
    assert source.index('        "signals",') < source.index('        "signal_targets",')
    assert source.index('        "signals",') < source.index('        "signal_events",')


def test_signal_service_revision_relaxes_only_directional_stop_constraint() -> None:
    source = SIGNAL_SERVICE_REVISION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = ast.literal_eval(node.value)

    assert assignments["revision"] == "20260901_0006"
    assert assignments["down_revision"] == "20260901_0005"
    assert "op.create_table(" not in source
    assert '"ck_signals_signal_stop_loss_direction"' in source
    assert "op.drop_constraint(" in source
    assert source.count('op.f("ck_signals_signal_stop_loss_direction")') == 2


def test_favorites_revision_extends_signal_service_with_one_table() -> None:
    source = FAVORITES_REVISION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = ast.literal_eval(node.value)

    assert assignments["revision"] == "20260901_0007"
    assert assignments["down_revision"] == "20260901_0006"
    assert source.count("op.create_table(") == 1
    assert '        "user_favorites",' in source
    assert 'ondelete="CASCADE"' in source
    assert 'name="uq_user_favorites_user_signal"' in source


def test_notification_settings_revision_extends_favorites_with_one_table() -> None:
    source = NOTIFICATION_SETTINGS_REVISION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = ast.literal_eval(node.value)

    assert assignments["revision"] == "20260902_0008"
    assert assignments["down_revision"] == "20260901_0007"
    assert source.count("op.create_table(") == 1
    assert '        "user_notification_settings",' in source
    assert 'ondelete="CASCADE"' in source
    assert 'name="uq_user_notification_settings_user_type"' in source
    for notification_type in (
        "NEW_SIGNAL",
        "TARGET_HIT",
        "STOP_HIT",
        "SIGNAL_UPDATED",
        "SIGNAL_CLOSED",
        "SYSTEM_NOTIFICATION",
    ):
        assert notification_type in source


def test_subscriptions_revision_extends_notifications_with_two_tables() -> None:
    source = SUBSCRIPTIONS_REVISION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = ast.literal_eval(node.value)

    assert assignments["revision"] == "20260902_0009"
    assert assignments["down_revision"] == "20260902_0008"
    assert source.count("op.create_table(") == 2
    assert '        "subscription_plans",' in source
    assert '        "subscriptions",' in source
    assert 'ondelete="RESTRICT"' in source
    assert '"uq_subscriptions_one_active_per_user"' in source
    assert "postgresql_where=sa.text(\"status = 'ACTIVE'\")" in source


def test_payments_revision_extends_subscriptions_with_one_table() -> None:
    source = PAYMENTS_REVISION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = ast.literal_eval(node.value)

    assert assignments["revision"] == "20260902_0010"
    assert assignments["down_revision"] == "20260902_0009"
    assert source.count("op.create_table(") == 1
    assert '        "payments",' in source
    assert source.count('ondelete="SET NULL"') == 3
    for status in ("PENDING", "SUCCESS", "FAILED", "CANCELLED"):
        assert status in source
    assert '"uq_payments_payment_reference"' in source
    assert '"uq_payments_provider_reference"' in source


def test_referrals_revision_extends_payments_with_one_table_and_user_code() -> None:
    source = REFERRALS_REVISION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = ast.literal_eval(node.value)

    assert assignments["revision"] == "20260902_0011"
    assert assignments["down_revision"] == "20260902_0010"
    assert source.count("op.create_table(") == 1
    assert '        "referrals",' in source
    assert '"referral_code"' in source
    assert source.count('ondelete="CASCADE"') == 2
    assert '"uq_referrals_referred_user_id"' in source
    assert '"ck_referrals_reward_disabled"' in source


def test_container_includes_alembic_runtime_files() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY --chown=bot:bot migrations ./migrations" in dockerfile
    assert "COPY --chown=bot:bot alembic.ini ./alembic.ini" in dockerfile
