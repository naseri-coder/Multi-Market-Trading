"""Convert successful gateway-independent payments into subscription entitlements."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.modules.operations.models import PaymentSettlementState
from app.modules.payments.models import Payment
from app.modules.subscriptions.models import Subscription, SubscriptionStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class PaymentSettlementService:
    def __init__(self, *, database, cutover_at: datetime) -> None:
        self.database = database
        self.cutover_at = cutover_at.astimezone(UTC)

    async def run_once(self, *, limit: int = 100) -> dict[str, int]:
        now = utc_now()
        settled = deferred = failed = 0
        async with self.database.session() as session, session.begin():
            # Expire stale ACTIVE subscriptions first so queued successful payments can settle.
            await session.execute(
                update(Subscription)
                .where(
                    Subscription.status == SubscriptionStatus.ACTIVE.value,
                    Subscription.expires_at <= now,
                )
                .values(
                    status=SubscriptionStatus.EXPIRED.value,
                    ended_at=now,
                    updated_at=now,
                )
            )

            payments = tuple(
                (
                    await session.scalars(
                        select(Payment)
                        .outerjoin(
                            PaymentSettlementState,
                            PaymentSettlementState.payment_id == Payment.id,
                        )
                        .where(
                            Payment.status == "SUCCESS",
                            Payment.subscription_id.is_(None),
                            Payment.finalized_at.is_not(None),
                            Payment.finalized_at > self.cutover_at,
                            (
                                PaymentSettlementState.payment_id.is_(None)
                                | (
                                    PaymentSettlementState.status.in_(("PENDING", "DEFERRED"))
                                    & (
                                        PaymentSettlementState.last_attempt_at.is_(None)
                                        | (PaymentSettlementState.last_attempt_at <= now - timedelta(hours=1))
                                    )
                                )
                            ),
                        )
                        .order_by(Payment.finalized_at, Payment.id)
                        .limit(limit)
                        .with_for_update(of=Payment, skip_locked=True)
                    )
                ).all()
            )

            for payment in payments:
                await session.execute(
                    insert(PaymentSettlementState)
                    .values(payment_id=payment.id, status="PENDING")
                    .on_conflict_do_nothing(index_elements=[PaymentSettlementState.payment_id])
                )
                state = await session.scalar(
                    select(PaymentSettlementState)
                    .where(PaymentSettlementState.payment_id == payment.id)
                    .with_for_update()
                )
                if state is None:
                    continue
                state.attempt_count += 1
                state.last_attempt_at = now
                state.updated_at = now

                if payment.user_id is None or payment.plan_id is None:
                    state.status = "FAILED"
                    state.last_error_code = "PAYMENT_MISSING_USER_OR_PLAN"
                    failed += 1
                    continue

                active = await session.scalar(
                    select(Subscription)
                    .where(
                        Subscription.user_id == payment.user_id,
                        Subscription.status == SubscriptionStatus.ACTIVE.value,
                    )
                    .with_for_update()
                )
                if active is not None:
                    state.status = "DEFERRED"
                    state.last_error_code = "ACTIVE_SUBSCRIPTION_EXISTS"
                    deferred += 1
                    continue

                starts_at = now
                subscription = Subscription(
                    user_id=payment.user_id,
                    plan_id=payment.plan_id,
                    status=SubscriptionStatus.ACTIVE.value,
                    starts_at=starts_at,
                    expires_at=starts_at + timedelta(days=payment.duration_days),
                    ended_at=None,
                    plan_name=payment.plan_name,
                    duration_days=payment.duration_days,
                    price=payment.amount,
                    currency=payment.currency,
                    created_at=now,
                    updated_at=now,
                )
                session.add(subscription)
                await session.flush()
                payment.subscription_id = subscription.id
                payment.updated_at = now
                state.status = "SETTLED"
                state.subscription_id = subscription.id
                state.last_error_code = None
                state.settled_at = now
                settled += 1

        return {"settled": settled, "deferred": deferred, "failed": failed}
