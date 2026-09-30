"""Add durable approvals and a distinct runner exit event; preserve existing data."""
from alembic import op
import sqlalchemy as sa

revision = "20260912_0019"
down_revision = "20260905_0018"
branch_labels = None
depends_on = None

OLD_EVENTS = (
    "'CREATED','UPDATED','PUBLISHED','ENTRY_ACTIVATED','TARGET_ADDED',"
    "'TARGET_HIT','STOP_LOSS_UPDATED','STOP_HIT','OUTCOME_AMBIGUOUS','CLOSED','CANCELLED'"
)


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS brooks_approved_market_evidence (
            source_signal_id varchar(128) PRIMARY KEY,
            exchange varchar(32) NOT NULL, market_type varchar(32) NOT NULL,
            symbol varchar(64) NOT NULL, timeframe varchar(16) NOT NULL,
            direction varchar(8) NOT NULL, always_in varchar(16) NOT NULL,
            candle_closed_at timestamptz NOT NULL,
            approved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            snapshot jsonb NOT NULL, context jsonb NOT NULL, gates jsonb NOT NULL
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_brooks_approval_market_time
        ON brooks_approved_market_evidence(exchange, market_type, symbol, timeframe, approved_at)
    """)
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("ALTER TABLE signal_events DROP CONSTRAINT IF EXISTS ck_signal_events_signal_event_type")
    op.create_check_constraint(op.f("ck_signal_events_signal_event_type"), "signal_events",
        "event_type IN (" + OLD_EVENTS + ",'RUNNER_CLOSED_ALWAYS_IN_REVERSAL')")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_signal_runner_reversal_once
        ON signal_events(signal_id)
        WHERE event_type = 'RUNNER_CLOSED_ALWAYS_IN_REVERSAL'
    """)
    # Third exit category, with partial returns distinct from whole-signal outcomes.
    op.execute("""
        CREATE OR REPLACE VIEW brooks_runner_reversal_outcomes AS
        SELECT e.signal_id, e.id AS event_id, e.created_at,
               e.metadata->>'evidence_source_signal_id' AS evidence_source_signal_id,
               (e.metadata->>'exit_fraction')::numeric AS exit_fraction,
               (e.metadata->>'weighted_return_pct')::numeric AS runner_return_pct,
               s.status AS signal_status, s.profit_loss AS final_signal_return_pct
        FROM signal_events e JOIN signals s ON s.id = e.signal_id
        WHERE e.event_type = 'RUNNER_CLOSED_ALWAYS_IN_REVERSAL'
    """)


def downgrade():
    # Never erase live approval/exit evidence to make a downgrade appear successful.
    if op.get_bind().scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM signal_events "
        "WHERE event_type='RUNNER_CLOSED_ALWAYS_IN_REVERSAL')"
    )):
        raise RuntimeError("runner exit evidence exists; downgrade would lose audit semantics")
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM brooks_approved_market_evidence)")):
        raise RuntimeError("approval evidence exists; retain additive schema during code rollback")
    op.execute("DROP VIEW IF EXISTS brooks_runner_reversal_outcomes")
    op.execute("DROP INDEX IF EXISTS uq_signal_runner_reversal_once")
    op.drop_constraint(op.f("ck_signal_events_signal_event_type"), "signal_events", type_="check")
    op.create_check_constraint(op.f("ck_signal_events_signal_event_type"), "signal_events",
                               "event_type IN (" + OLD_EVENTS + ")")
    op.execute("DROP TABLE IF EXISTS brooks_approved_market_evidence")
