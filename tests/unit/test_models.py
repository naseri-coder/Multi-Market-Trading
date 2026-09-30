"""Metadata-level tests for current ORM models."""

from sqlalchemy import BigInteger, CheckConstraint, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import configure_mappers

from app.db.base import Base
from app.db.models import (
    Admin,
    BotSetting,
    Broadcast,
    BroadcastRecipient,
    Channel,
    Payment,
    Referral,
    Signal,
    SignalEvent,
    SignalTarget,
    SupportMessage,
    SupportTicket,
    Subscription,
    SubscriptionPlan,
    User,
    UserFavorite,
    UserNotificationSetting,
)


def constraint_names(model: type) -> set[str]:
    """Return all named table constraints for a mapped model."""
    return {constraint.name for constraint in model.__table__.constraints if constraint.name}


def test_metadata_contains_current_tables() -> None:
    assert set(Base.metadata.tables) == {
        "brooks_approved_market_evidence",
        "brooks_positions",
        "brooks_position_entry_lots",
        "brooks_position_exit_fills",
        "brooks_position_scale_events",
        "brooks_position_risk_snapshots",
        "users",
        "admins",
        "channels",
        "bot_settings",
        "broadcasts",
        "broadcast_recipients",
        "support_tickets",
        "support_messages",
        "signals",
        "signal_targets",
        "signal_events",
        "user_favorites",
        "user_notification_settings",
        "subscription_plans",
        "subscriptions",
        "payments",
        "referrals",
        "signal_automation_metadata",
        "signal_rule_evidence",
        "signal_deliveries",
        "signal_quality_assessments",
        "signal_lifecycle_states",
        "vip_entitlement_states",
        "payment_settlement_states",
        "runtime_health",
        "performance_metrics",
        "pattern_statistics",
        "failure_analysis",
        "decision_quality_scores",
    }


def test_models_use_bigint_identity_primary_keys() -> None:
    for model in (
        User,
        Admin,
        Channel,
        BotSetting,
        Broadcast,
        BroadcastRecipient,
        SupportTicket,
        SupportMessage,
        Signal,
        SignalTarget,
        SignalEvent,
        UserFavorite,
        UserNotificationSetting,
        SubscriptionPlan,
        Subscription,
        Payment,
        Referral,
    ):
        column = model.__table__.c.id
        assert isinstance(column.type, BigInteger)
        assert column.primary_key is True
        assert column.identity is not None


def test_core_unique_constraints_are_database_enforced() -> None:
    assert "uq_users_telegram_user_id" in constraint_names(User)
    assert "uq_admins_user_id" in constraint_names(Admin)
    assert "uq_channels_telegram_chat_id" in constraint_names(Channel)
    assert "uq_bot_settings_key" in constraint_names(BotSetting)
    assert any(isinstance(item, UniqueConstraint) for item in User.__table__.constraints)


def test_status_and_order_constraints_are_named() -> None:
    checks = {
        constraint.name
        for table in (User.__table__, Channel.__table__, BotSetting.__table__)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert checks == {
        "ck_users_user_status",
        "ck_users_valid_referral_code",
        "ck_channels_non_negative_sort_order",
        "ck_bot_settings_value_type",
    }


def test_timestamp_columns_are_timezone_aware() -> None:
    for model in (
        User,
        Admin,
        Channel,
        BotSetting,
        Broadcast,
        BroadcastRecipient,
        SupportTicket,
        SupportMessage,
        Signal,
        SignalTarget,
    ):
        assert model.__table__.c.created_at.type.timezone is True
        assert model.__table__.c.updated_at.type.timezone is True

    assert User.__table__.c.last_activity.type.timezone is True
    assert Signal.__table__.c.closed_at.type.timezone is True
    assert SignalTarget.__table__.c.hit_at.type.timezone is True
    assert SignalEvent.__table__.c.created_at.type.timezone is True
    assert UserFavorite.__table__.c.created_at.type.timezone is True
    assert UserNotificationSetting.__table__.c.created_at.type.timezone is True
    assert UserNotificationSetting.__table__.c.updated_at.type.timezone is True
    assert SubscriptionPlan.__table__.c.created_at.type.timezone is True
    assert SubscriptionPlan.__table__.c.updated_at.type.timezone is True
    assert Subscription.__table__.c.starts_at.type.timezone is True
    assert Subscription.__table__.c.expires_at.type.timezone is True
    assert Subscription.__table__.c.ended_at.type.timezone is True
    assert Payment.__table__.c.finalized_at.type.timezone is True
    assert Payment.__table__.c.created_at.type.timezone is True
    assert Payment.__table__.c.updated_at.type.timezone is True
    assert Referral.__table__.c.created_at.type.timezone is True


def test_admin_and_setting_foreign_keys_have_safe_delete_actions() -> None:
    admin_fk = next(iter(Admin.__table__.c.user_id.foreign_keys))
    setting_fk = next(iter(BotSetting.__table__.c.updated_by_admin_id.foreign_keys))

    assert admin_fk.target_fullname == "users.id"
    assert admin_fk.ondelete == "CASCADE"
    assert setting_fk.target_fullname == "admins.id"
    assert setting_fk.ondelete == "SET NULL"


def test_postgresql_jsonb_is_used_for_typed_settings() -> None:
    assert isinstance(BotSetting.__table__.c.value.type, JSONB)


def test_relationship_mappers_configure_successfully() -> None:
    configure_mappers()

    assert User.admin.property.uselist is False
    assert Admin.user.property.uselist is False


def test_broadcast_recipient_foreign_keys_cascade_and_snapshot_is_unique() -> None:
    broadcast_fk = next(iter(BroadcastRecipient.__table__.c.broadcast_id.foreign_keys))
    user_fk = next(iter(BroadcastRecipient.__table__.c.user_id.foreign_keys))

    assert broadcast_fk.target_fullname == "broadcasts.id"
    assert broadcast_fk.ondelete == "CASCADE"
    assert user_fk.target_fullname == "users.id"
    assert user_fk.ondelete == "CASCADE"
    assert "uq_broadcast_recipients_broadcast_user" in constraint_names(BroadcastRecipient)


def test_broadcast_tables_have_named_state_and_shape_checks() -> None:
    checks = {
        constraint.name
        for table in (Broadcast.__table__, BroadcastRecipient.__table__)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert checks == {
        "ck_broadcasts_broadcast_content_type",
        "ck_broadcasts_broadcast_status",
        "ck_broadcasts_broadcast_media_type",
        "ck_broadcasts_broadcast_content_shape",
        "ck_broadcasts_broadcast_non_negative_counts",
        "ck_broadcast_recipients_broadcast_recipient_status",
        "ck_broadcast_recipients_broadcast_recipient_attempts",
    }


def test_forward_source_columns_are_nullable_until_content_type_requires_them() -> None:
    assert isinstance(Broadcast.__table__.c.source_chat_id.type, BigInteger)
    assert Broadcast.__table__.c.source_chat_id.nullable is True
    assert Broadcast.__table__.c.source_message_id.nullable is True


def test_support_foreign_keys_and_state_constraints_are_database_enforced() -> None:
    ticket_user_fk = next(iter(SupportTicket.__table__.c.user_id.foreign_keys))
    message_ticket_fk = next(iter(SupportMessage.__table__.c.ticket_id.foreign_keys))
    checks = {
        constraint.name
        for table in (SupportTicket.__table__, SupportMessage.__table__)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert ticket_user_fk.target_fullname == "users.id"
    assert ticket_user_fk.ondelete == "CASCADE"
    assert message_ticket_fk.target_fullname == "support_tickets.id"
    assert message_ticket_fk.ondelete == "CASCADE"
    assert checks == {
        "ck_support_tickets_support_ticket_status",
        "ck_support_messages_support_message_sender_role",
    }


def test_signal_numeric_precision_and_json_event_metadata_are_explicit() -> None:
    for column_name in ("entry_price", "stop_loss"):
        column_type = Signal.__table__.c[column_name].type
        assert isinstance(column_type, Numeric)
        assert column_type.precision == 38
        assert column_type.scale == 18

    target_price = SignalTarget.__table__.c.target_price.type
    assert isinstance(target_price, Numeric)
    assert target_price.precision == 38
    assert target_price.scale == 18
    assert isinstance(SignalEvent.__table__.c.metadata.type, JSONB)


def test_signal_foreign_keys_cascade_and_target_number_is_unique() -> None:
    target_fk = next(iter(SignalTarget.__table__.c.signal_id.foreign_keys))
    event_fk = next(iter(SignalEvent.__table__.c.signal_id.foreign_keys))

    assert target_fk.target_fullname == "signals.id"
    assert target_fk.ondelete == "CASCADE"
    assert event_fk.target_fullname == "signals.id"
    assert event_fk.ondelete == "CASCADE"
    assert "uq_signal_targets_signal_target_number" in constraint_names(SignalTarget)


def test_signal_state_and_integrity_checks_are_database_enforced() -> None:
    signal_checks = {
        constraint.name
        for constraint in Signal.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    target_checks = {
        constraint.name
        for constraint in SignalTarget.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    event_checks = {
        constraint.name
        for constraint in SignalEvent.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert signal_checks == {
        "ck_signals_signal_direction",
        "ck_signals_signal_status",
        "ck_signals_signal_symbol",
        "ck_signals_signal_positive_values",
        "ck_signals_signal_closed_at_status",
        "ck_signals_signal_publication_scope",
    }
    assert target_checks == {
        "ck_signal_targets_signal_target_positive_number",
        "ck_signal_targets_signal_target_positive_price",
        "ck_signal_targets_signal_target_status",
        "ck_signal_targets_signal_target_hit_state",
    }
    assert event_checks == {
        "ck_signal_events_signal_event_type",
        "ck_signal_events_signal_event_metadata_object",
    }


def test_signal_relationships_configure_with_delete_orphan_cascades() -> None:
    configure_mappers()

    assert Signal.targets.property.back_populates == "signal"
    assert Signal.events.property.back_populates == "signal"
    assert "delete-orphan" in Signal.targets.property.cascade
    assert "delete-orphan" in Signal.events.property.cascade
    assert Signal.targets.property.passive_deletes is True
    assert Signal.events.property.passive_deletes is True


def test_favorite_foreign_keys_cascade_and_pair_is_unique() -> None:
    user_fk = next(iter(UserFavorite.__table__.c.user_id.foreign_keys))
    signal_fk = next(iter(UserFavorite.__table__.c.signal_id.foreign_keys))

    assert user_fk.target_fullname == "users.id"
    assert user_fk.ondelete == "CASCADE"
    assert signal_fk.target_fullname == "signals.id"
    assert signal_fk.ondelete == "CASCADE"
    assert "uq_user_favorites_user_signal" in constraint_names(UserFavorite)


def test_favorite_relationships_are_delete_orphan_and_passive() -> None:
    configure_mappers()

    assert User.favorites.property.back_populates == "user"
    assert Signal.favorites.property.back_populates == "signal"
    assert "delete-orphan" in User.favorites.property.cascade
    assert "delete-orphan" in Signal.favorites.property.cascade
    assert User.favorites.property.passive_deletes is True
    assert Signal.favorites.property.passive_deletes is True


def test_notification_setting_integrity_and_user_cascade_are_enforced() -> None:
    user_fk = next(
        iter(UserNotificationSetting.__table__.c.user_id.foreign_keys)
    )
    checks = {
        constraint.name
        for constraint in UserNotificationSetting.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert user_fk.target_fullname == "users.id"
    assert user_fk.ondelete == "CASCADE"
    assert "uq_user_notification_settings_user_type" in constraint_names(
        UserNotificationSetting
    )
    assert checks == {
        "ck_user_notification_settings_notification_type"
    }


def test_notification_setting_relationship_is_delete_orphan_and_passive() -> None:
    configure_mappers()

    assert User.notification_settings.property.back_populates == "user"
    assert "delete-orphan" in User.notification_settings.property.cascade
    assert User.notification_settings.property.passive_deletes is True


def test_subscription_foreign_keys_checks_and_partial_unique_index() -> None:
    user_fk = next(iter(Subscription.__table__.c.user_id.foreign_keys))
    plan_fk = next(iter(Subscription.__table__.c.plan_id.foreign_keys))
    plan_checks = {
        item.name
        for item in SubscriptionPlan.__table__.constraints
        if isinstance(item, CheckConstraint)
    }
    subscription_checks = {
        item.name
        for item in Subscription.__table__.constraints
        if isinstance(item, CheckConstraint)
    }
    indexes = {item.name: item for item in Subscription.__table__.indexes}

    assert user_fk.target_fullname == "users.id"
    assert user_fk.ondelete == "CASCADE"
    assert plan_fk.target_fullname == "subscription_plans.id"
    assert plan_fk.ondelete == "RESTRICT"
    assert plan_checks == {
        "ck_subscription_plans_valid_name",
        "ck_subscription_plans_positive_duration",
        "ck_subscription_plans_non_negative_price",
        "ck_subscription_plans_valid_currency",
    }
    assert subscription_checks == {
        "ck_subscriptions_status",
        "ck_subscriptions_valid_period",
        "ck_subscriptions_status_end_state",
        "ck_subscriptions_positive_duration",
        "ck_subscriptions_non_negative_price",
        "ck_subscriptions_valid_plan_name",
        "ck_subscriptions_valid_currency",
    }
    active_index = indexes["uq_subscriptions_one_active_per_user"]
    assert active_index.unique is True
    assert str(active_index.dialect_options["postgresql"]["where"]) == (
        "status = 'ACTIVE'"
    )


def test_subscription_relationships_preserve_plan_history_and_cascade_users() -> None:
    configure_mappers()

    assert User.subscriptions.property.back_populates == "user"
    assert SubscriptionPlan.subscriptions.property.back_populates == "plan"
    assert "delete-orphan" in User.subscriptions.property.cascade
    assert User.subscriptions.property.passive_deletes is True
    assert SubscriptionPlan.subscriptions.property.passive_deletes is True


def test_payment_constraints_indexes_and_audit_foreign_keys() -> None:
    user_fk = next(iter(Payment.__table__.c.user_id.foreign_keys))
    plan_fk = next(iter(Payment.__table__.c.plan_id.foreign_keys))
    subscription_fk = next(
        iter(Payment.__table__.c.subscription_id.foreign_keys)
    )
    checks = {
        item.name
        for item in Payment.__table__.constraints
        if isinstance(item, CheckConstraint)
    }
    indexes = {item.name: item for item in Payment.__table__.indexes}

    assert user_fk.ondelete == "SET NULL"
    assert plan_fk.ondelete == "SET NULL"
    assert subscription_fk.ondelete == "SET NULL"
    assert checks == {
        "ck_payments_status",
        "ck_payments_valid_payment_reference",
        "ck_payments_positive_telegram_user_id",
        "ck_payments_valid_plan_name",
        "ck_payments_positive_duration",
        "ck_payments_positive_amount",
        "ck_payments_valid_currency",
        "ck_payments_status_finalized_state",
        "ck_payments_failure_reason_state",
        "ck_payments_provider_reference_state",
        "ck_payments_valid_provider",
        "ck_payments_valid_provider_reference",
        "ck_payments_valid_failure_reason",
    }
    assert "uq_payments_payment_reference" in constraint_names(Payment)
    assert "uq_payments_subscription_id" in constraint_names(Payment)
    provider_index = indexes["uq_payments_provider_reference"]
    assert provider_index.unique is True
    assert str(provider_index.dialect_options["postgresql"]["where"]) == (
        "provider_reference IS NOT NULL"
    )


def test_payment_relationships_preserve_audit_rows_on_parent_deletion() -> None:
    configure_mappers()

    assert User.payments.property.back_populates == "user"
    assert SubscriptionPlan.payments.property.back_populates == "plan"
    assert Subscription.payment.property.back_populates == "subscription"
    assert User.payments.property.passive_deletes is True
    assert SubscriptionPlan.payments.property.passive_deletes is True
    assert Subscription.payment.property.passive_deletes is True


def test_referral_constraints_relationships_and_reward_disable_are_enforced() -> None:
    referrer_fk = next(iter(Referral.__table__.c.referrer_user_id.foreign_keys))
    referred_fk = next(iter(Referral.__table__.c.referred_user_id.foreign_keys))
    checks = {
        item.name
        for item in Referral.__table__.constraints
        if isinstance(item, CheckConstraint)
    }

    assert referrer_fk.target_fullname == "users.id"
    assert referrer_fk.ondelete == "CASCADE"
    assert referred_fk.target_fullname == "users.id"
    assert referred_fk.ondelete == "CASCADE"
    assert "uq_users_referral_code" in constraint_names(User)
    assert "uq_referrals_referred_user_id" in constraint_names(Referral)
    assert checks == {
        "ck_referrals_different_users",
        "ck_referrals_valid_referral_code",
        "ck_referrals_reward_disabled",
    }

    configure_mappers()
    assert User.referrals_sent.property.back_populates == "referrer"
    assert User.referral_received.property.back_populates == "referred_user"
    assert "delete-orphan" in User.referrals_sent.property.cascade
    assert "delete-orphan" in User.referral_received.property.cascade
    assert User.referrals_sent.property.passive_deletes is True
    assert User.referral_received.property.passive_deletes is True
