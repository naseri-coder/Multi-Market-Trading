"""Production operations: lifecycle, VIP entitlement, settlement and health.

Revision ID: 20260902_0016
Revises: 20260902_0015
Create Date: 2026-09-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260902_0016"
down_revision = "20260902_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_signal_events_signal_event_type"),
        "signal_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_signal_events_signal_event_type"),
        "signal_events",
        "event_type IN ('CREATED','UPDATED','PUBLISHED','ENTRY_ACTIVATED',"
        "'TARGET_ADDED','TARGET_HIT','STOP_LOSS_UPDATED','STOP_HIT',"
        "'OUTCOME_AMBIGUOUS','CLOSED','CANCELLED')",
    )

    op.create_table(
        "signal_lifecycle_states",
        sa.Column("signal_id", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=24), server_default="WAITING_ENTRY", nullable=False),
        sa.Column("entry_activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_processed_candle_close", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_market_price", sa.Numeric(38, 18), nullable=True),
        sa.Column("last_message_event_id", sa.BigInteger(), nullable=True),
        sa.Column("ambiguous_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "state IN ('WAITING_ENTRY','ACTIVE','COMPLETE','AMBIGUOUS')",
            name=op.f("ck_signal_lifecycle_states_state"),
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"], ["signals.id"], ondelete="CASCADE",
            name=op.f("fk_signal_lifecycle_states_signal_id_signals"),
        ),
        sa.PrimaryKeyConstraint("signal_id", name=op.f("pk_signal_lifecycle_states")),
    )

    op.create_table(
        "vip_entitlement_states",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("desired_active", sa.Boolean(), nullable=False),
        sa.Column("membership_state", sa.String(length=24), server_default="UNKNOWN", nullable=False),
        sa.Column("last_invite_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_invite_link", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "membership_state IN ('UNKNOWN','MEMBER','INVITE_SENT','REMOVED','ADMIN_UNMANAGED','ERROR')",
            name=op.f("ck_vip_entitlement_states_membership_state"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name=op.f("fk_vip_entitlement_states_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_vip_entitlement_states")),
    )

    op.create_table(
        "payment_settlement_states",
        sa.Column("payment_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="PENDING", nullable=False),
        sa.Column("subscription_id", sa.BigInteger(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING','SETTLED','DEFERRED','FAILED')",
            name=op.f("ck_payment_settlement_states_status"),
        ),
        sa.CheckConstraint("attempt_count >= 0", name=op.f("ck_payment_settlement_states_attempt_count")),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payments.id"], ondelete="CASCADE",
            name=op.f("fk_payment_settlement_states_payment_id_payments"),
        ),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="SET NULL",
            name=op.f("fk_payment_settlement_states_subscription_id_subscriptions"),
        ),
        sa.PrimaryKeyConstraint("payment_id", name=op.f("pk_payment_settlement_states")),
    )

    op.create_table(
        "runtime_health",
        sa.Column("component", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('OK','DEGRADED','ERROR')", name=op.f("ck_runtime_health_status")),
        sa.PrimaryKeyConstraint("component", name=op.f("pk_runtime_health")),
    )


def downgrade() -> None:
    op.drop_table("runtime_health")
    op.drop_table("payment_settlement_states")
    op.drop_table("vip_entitlement_states")
    op.drop_table("signal_lifecycle_states")

    op.drop_constraint(
        op.f("ck_signal_events_signal_event_type"),
        "signal_events",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_signal_events_signal_event_type"),
        "signal_events",
        "event_type IN ('CREATED','UPDATED','PUBLISHED','TARGET_ADDED',"
        "'TARGET_HIT','STOP_LOSS_UPDATED','STOP_HIT','CLOSED','CANCELLED')",
    )
