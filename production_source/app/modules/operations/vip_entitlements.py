"""Synchronize active subscription entitlements with the private VIP Telegram channel."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from telegram import Bot
from telegram.error import BadRequest, TelegramError

from app.modules.operations.models import VipEntitlementState
from app.modules.subscriptions.models import Subscription, SubscriptionStatus
from app.modules.users.models import User

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


class VipEntitlementService:
    def __init__(
        self,
        *,
        database,
        bot: Bot,
        vip_channel_id: int,
        invite_ttl_hours: int,
    ) -> None:
        self.database = database
        self.bot = bot
        self.vip_channel_id = vip_channel_id
        self.invite_ttl = timedelta(hours=invite_ttl_hours)

    async def run_once(self) -> dict[str, int]:
        now = utc_now()
        async with self.database.session() as session, session.begin():
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

            active_users = tuple(
                (
                    await session.execute(
                        select(User.id, User.telegram_user_id)
                        .join(Subscription, Subscription.user_id == User.id)
                        .where(
                            Subscription.status == SubscriptionStatus.ACTIVE.value,
                            Subscription.expires_at > now,
                            User.is_bot.is_(False),
                        )
                        .order_by(User.id)
                    )
                ).all()
            )
            managed_ids = set(
                (
                    await session.scalars(select(VipEntitlementState.user_id))
                ).all()
            )
            active_map = {int(user_id): int(telegram_id) for user_id, telegram_id in active_users}
            candidate_ids = sorted(set(active_map) | managed_ids)
            users = {
                user.id: user
                for user in (
                    await session.scalars(select(User).where(User.id.in_(candidate_ids)))
                ).all()
            } if candidate_ids else {}

        invited = removed = members = errors = 0
        for user_id in candidate_ids:
            user = users.get(user_id)
            if user is None:
                continue
            desired = user_id in active_map
            try:
                outcome = await self._sync_one(
                    user_id=user_id,
                    telegram_user_id=user.telegram_user_id,
                    desired_active=desired,
                    now=now,
                )
                invited += int(outcome == "INVITE_SENT")
                removed += int(outcome == "REMOVED")
                members += int(outcome == "MEMBER")
            except TelegramError as exc:
                errors += 1
                await self._store_state(
                    user_id=user_id,
                    desired_active=desired,
                    membership_state="ERROR",
                    now=now,
                    error_code=type(exc).__name__,
                )
                logger.warning(
                    "VIP entitlement Telegram synchronization failed",
                    extra={
                        "event": "vip_entitlement_sync_failed",
                        "user_id": user_id,
                        "error_code": type(exc).__name__,
                    },
                )
        return {"members": members, "invited": invited, "removed": removed, "errors": errors}

    async def _sync_one(
        self,
        *,
        user_id: int,
        telegram_user_id: int,
        desired_active: bool,
        now: datetime,
    ) -> str:
        try:
            member = await self.bot.get_chat_member(self.vip_channel_id, telegram_user_id)
            status = str(member.status).lower()
        except BadRequest as exc:
            if desired_active and "user not found" in str(exc).lower():
                status = "left"
            else:
                raise
        is_member = status in {"member", "administrator", "creator", "owner"}
        is_admin = status in {"administrator", "creator", "owner"}

        if desired_active:
            if is_member:
                previous = await self._load_state(user_id)
                if previous is not None and previous.active_invite_link:
                    try:
                        await self.bot.revoke_chat_invite_link(
                            self.vip_channel_id, previous.active_invite_link
                        )
                    except TelegramError:
                        logger.warning(
                            "Unable to revoke consumed VIP invite link",
                            extra={"event": "vip_invite_revoke_failed", "user_id": user_id},
                        )
                state = "ADMIN_UNMANAGED" if is_admin else "MEMBER"
                await self._store_state(
                    user_id=user_id,
                    desired_active=True,
                    membership_state=state,
                    now=now,
                    clear_invite=True,
                )
                return "MEMBER"

            if status in {"kicked", "banned"}:
                await self.bot.unban_chat_member(
                    self.vip_channel_id,
                    telegram_user_id,
                    only_if_banned=True,
                )

            previous = await self._load_state(user_id)
            if (
                previous is not None
                and previous.last_invite_sent_at is not None
                and now - previous.last_invite_sent_at < self.invite_ttl
            ):
                await self._store_state(
                    user_id=user_id,
                    desired_active=True,
                    membership_state="INVITE_SENT",
                    now=now,
                    invite_sent_at=previous.last_invite_sent_at,
                )
                return "INVITE_SENT"

            link = await self.bot.create_chat_invite_link(
                chat_id=self.vip_channel_id,
                expire_date=now + self.invite_ttl,
                member_limit=1,
                name=f"subscription-{user_id}-{int(now.timestamp())}",
            )
            await self.bot.send_message(
                chat_id=telegram_user_id,
                text=(
                    "💎 اشتراک VIP شما فعال است.\n\n"
                    "لینک یک‌بارمصرف ورود به کانال VIP:\n"
                    f"{link.invite_link}\n\n"
                    "این لینک محدود و زمان‌دار است."
                ),
            )
            await self._store_state(
                user_id=user_id,
                desired_active=True,
                membership_state="INVITE_SENT",
                now=now,
                invite_sent_at=now,
                active_invite_link=link.invite_link,
            )
            return "INVITE_SENT"

        previous = await self._load_state(user_id)
        if previous is not None and previous.active_invite_link:
            try:
                await self.bot.revoke_chat_invite_link(
                    self.vip_channel_id, previous.active_invite_link
                )
            except TelegramError:
                logger.warning(
                    "Unable to revoke expired VIP invite link",
                    extra={"event": "vip_invite_revoke_failed", "user_id": user_id},
                )

        if is_admin:
            await self._store_state(
                user_id=user_id,
                desired_active=False,
                membership_state="ADMIN_UNMANAGED",
                now=now,
                clear_invite=True,
            )
            return "ADMIN_UNMANAGED"

        if is_member:
            await self.bot.ban_chat_member(self.vip_channel_id, telegram_user_id)
            await self.bot.unban_chat_member(
                self.vip_channel_id,
                telegram_user_id,
                only_if_banned=True,
            )
        await self._store_state(
            user_id=user_id,
            desired_active=False,
            membership_state="REMOVED",
            now=now,
            clear_invite=True,
        )
        return "REMOVED"

    async def _load_state(self, user_id: int) -> VipEntitlementState | None:
        async with self.database.session() as session:
            return await session.get(VipEntitlementState, user_id)

    async def _store_state(
        self,
        *,
        user_id: int,
        desired_active: bool,
        membership_state: str,
        now: datetime,
        invite_sent_at: datetime | None = None,
        active_invite_link: str | None = None,
        clear_invite: bool = False,
        error_code: str | None = None,
    ) -> None:
        values = {
            "desired_active": desired_active,
            "membership_state": membership_state,
            "last_synced_at": now,
            "last_error_code": error_code,
            "updated_at": now,
        }
        if invite_sent_at is not None:
            values["last_invite_sent_at"] = invite_sent_at
        if active_invite_link is not None:
            values["active_invite_link"] = active_invite_link
        elif clear_invite:
            values["active_invite_link"] = None
        async with self.database.session() as session, session.begin():
            statement = insert(VipEntitlementState).values(
                user_id=user_id,
                desired_active=desired_active,
                membership_state=membership_state,
                last_invite_sent_at=invite_sent_at,
                active_invite_link=active_invite_link,
                last_synced_at=now,
                last_error_code=error_code,
                updated_at=now,
            ).on_conflict_do_update(
                index_elements=[VipEntitlementState.user_id],
                set_=values,
            )
            await session.execute(statement)
