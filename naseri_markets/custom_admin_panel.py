"""Opt-in Telegram admin panel for public trusted Custom PAPER engines.

Register handlers on the *same* trusted Telegram Application, after the
existing admin handlers. Do not run a second bot poller or alter frozen v0.3.2
production_source. Optional python-telegram-bot extra; no network on import.
No live signal publication: saved private destinations remain DISABLED.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

from .trusted_custom import LocalCustomRefused, TrustedLocalCustomHost

MENU_LABEL = "🎛 مدیریت هسته‌های Custom"
_PENDING = "mmt_custom_admin_pending"
_TOKEN = re.compile(r"[0-9a-f]{12}\Z")
_ACTION = re.compile(r"cm:(list|open|enable|disable|route|clear|paper|audit|back):?([0-9a-f]{12})?:?([0-9]+)?\Z")


class AdminCustomPanelRefused(ValueError):
    """Unauthorized chat, stale action or unsafe delivery destination."""


def _token(engine_id: str) -> str:
    return hashlib.sha256(engine_id.encode("utf-8")).hexdigest()[:12]


def _resolve(host: TrustedLocalCustomHost, token: str):
    if not _TOKEN.fullmatch(token):
        raise AdminCustomPanelRefused("CUSTOM_CALLBACK_UNKNOWN")
    matches = [state for state in host.list() if _token(state.engine_id) == token]
    if len(matches) != 1:
        raise AdminCustomPanelRefused("CUSTOM_CALLBACK_UNIQUE_ENGINE_REQUIRED")
    return matches[0]


def _private_admin(update, admin_ids: frozenset[int]) -> bool:
    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    return (chat is not None and getattr(chat, "type", None) == "private"
            and user is not None and type(user.id) is int
            and user.id in admin_ids and getattr(chat, "id", None) == user.id)


def _safe_title(value: str) -> str:
    # Never echo unbounded Telegram channel titles in private admin panels.
    title = " ".join(value.split())
    return title[:100] if title else "کانال خصوصی"


@dataclass(frozen=True, slots=True)
class CustomAdminPanel:
    state_dir: Path
    admin_ids: frozenset[int]

    def __init__(self, *, state_dir: str | Path, admin_ids: Collection[int]):
        allowed = frozenset(admin_ids)
        if not allowed or any(type(x) is not int or x <= 0 for x in allowed):
            raise AdminCustomPanelRefused("CUSTOM_EXPLICIT_ADMIN_IDS_REQUIRED")
        object.__setattr__(self, "state_dir", Path(state_dir))
        object.__setattr__(self, "admin_ids", allowed)

    def _open(self) -> TrustedLocalCustomHost:
        return TrustedLocalCustomHost(self.state_dir)

    def keyboard(self, host: TrustedLocalCustomHost, selected: str | None = None):
        from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup
        if selected is None:
            rows = [
                [Button(f"{'✅' if item.enabled else '⏸'} {item.engine_id}",
                        callback_data=f"cm:open:{_token(item.engine_id)}")]
                for item in host.list()[:30]]
            rows.extend([
                [Button("🔄 تازه‌سازی", callback_data="cm:list")],
                [Button("📦 ثبت هسته جدید: از CLI", callback_data="cm:back")],
            ])
            return InlineKeyboardMarkup(rows)
        state = host.get(selected)
        if state is None:
            raise AdminCustomPanelRefused("CUSTOM_UNKNOWN_ENGINE")
        idtoken = _token(selected)
        rows = [[Button(
            "⏸ غیرفعال‌سازی" if state.enabled else "✅ فعال‌سازی PAPER",
            callback_data=f"cm:{'disable' if state.enabled else 'enable'}:"
                          f"{idtoken}:{state.revision}")]]
        rows.append([Button("📤 تعیین کانال خصوصی", callback_data=f"cm:route:{idtoken}"),
                     Button("🗑 پاک‌کردن مسیر", callback_data=f"cm:clear:{idtoken}")])
        rows.append([Button("🧾 آخرین سیگنال‌های PAPER",
                            callback_data=f"cm:paper:{idtoken}"),
                     Button("📋 تاریخچه تغییرات", callback_data=f"cm:audit:{idtoken}")])
        rows.append([Button("🔙 فهرست هسته‌ها", callback_data="cm:list")])
        return InlineKeyboardMarkup(rows)

    def summary(self, host: TrustedLocalCustomHost) -> str:
        engines = host.list()
        enabled = sum(item.enabled for item in engines)
        return (
            "🎛 مدیریت هسته‌های Custom\n\n"
            f"هسته‌های ثبت‌شده: {len(engines)} | فعال در PAPER: {enabled}\n"
            "مقصدهای کانال: فقط ذخیره تنظیمات؛ ارسال خودکار غیرفعال 🔒\n"
            "اجرای هسته فقط محلی و با تأیید صریح اپراتور انجام می‌شود.\n"
            "ثبت سورس و تأیید هش همچنان از مسیر امن CLI است.")

    def detail(self, host: TrustedLocalCustomHost, engine_id: str) -> str:
        state = host.get(engine_id)
        if state is None:
            raise AdminCustomPanelRefused("CUSTOM_UNKNOWN_ENGINE")
        route = host.route(engine_id)
        signals = host.signals(engine_id)
        return (
            f"🎛 {engine_id} — نسخه {state.engine_version}\n\n"
            f"حالت: {'✅ PAPER فعال' if state.enabled else '⏸ غیرفعال'}\n"
            f"نسل تنظیمات: {state.revision}\n"
            f"قرارداد: {state.descriptor_sha256[:16]}…\n"
            f"سیگنال‌های PAPER: {len(signals)}\n"
            f"کانال ذخیره‌شده: {_safe_title(route['channel_title']) if route['channel_id'] else 'ندارد'}\n"
            f"شناسه کانال: {route['channel_id'] or '—'}\n"
            "انتشار خودکار: 🔒 غیرفعال\n"
            "پیش‌نمایش سیگنال‌ها فقط در گفت‌وگوی خصوصی مدیر انجام می‌شود.")

    async def panel(self, update, context) -> None:
        if not _private_admin(update, self.admin_ids):
            return
        context.user_data.pop(_PENDING, None)
        msg = update.effective_message
        if msg is None:
            return
        with self._open() as host:
            await msg.reply_text(self.summary(host), reply_markup=self.keyboard(host))

    async def callback(self, update, context) -> None:
        query = getattr(update, "callback_query", None)
        if query is None or not _private_admin(update, self.admin_ids):
            if query is not None:
                await query.answer("دسترسی مجاز نیست", show_alert=True)
            return
        m = _ACTION.fullmatch(query.data or "")
        if m is None:
            await query.answer("عملیات نامعتبر", show_alert=True)
            return
        command, token, revision = m.groups()
        await query.answer()
        context.user_data.pop(_PENDING, None)
        try:
            with self._open() as host:
                if command in ("list", "back"):
                    text = self.summary(host)
                    markup = self.keyboard(host)
                else:
                    state = _resolve(host, token)
                    engine_id = state.engine_id
                    if command in ("enable", "disable"):
                        if revision is None:
                            raise AdminCustomPanelRefused("CUSTOM_REVISION_REQUIRED")
                        host.toggle_as_admin(
                            engine_id, enabled=command == "enable",
                            expected_revision=int(revision),
                            descriptor_sha256=state.descriptor_sha256,
                            actor_id=update.effective_user.id)
                    elif command == "route":
                        context.user_data[_PENDING] = (
                            engine_id, state.revision, update.effective_user.id)
                        text = (
                            "شناسه عددی کانال خصوصی (مثلاً -100...) را ارسال کنید.\n"
                            "ربات باید Administrator کانال و دارای اجازه ارسال باشد.\n"
                            "کانال صرفاً برای استفاده احتمالی آینده ثبت می‌شود؛"
                            " ارسال خودکار PAPER فعال نخواهد شد.")
                        markup = self.keyboard(host, engine_id)
                        if query.message is not None:
                            await query.message.reply_text(text, reply_markup=markup)
                        return
                    elif command == "clear":
                        host.clear_route(engine_id, actor_id=update.effective_user.id)
                    elif command == "paper":
                        signals = host.signals(engine_id)
                        preview = signals[-3:]
                        lines = [
                            f"{x['signal_id']} | {x['symbol']} | {x['direction']} "
                            f"| entry={x['entry']} stop={x['stop']}"
                            for x in preview]
                        text = "🧾 آخرین سیگنال‌های PAPER (فقط مدیر)\n" + (
                            "\n".join(lines) if lines else "هنوز سیگنالی نیست")
                        markup = self.keyboard(host, engine_id)
                        if query.message is not None:
                            await query.message.reply_text(text, reply_markup=markup)
                        return
                    elif command == "audit":
                        history = host.admin_history(engine_id)[:8]
                        text = "📋 تغییرات مدیریتی\n" + (
                            "\n".join(
                                f"{x['action']} | {x['engine_revision']} | "
                                f"{x['created_at']}" for x in history)
                            if history else "هنوز تغییری ثبت نشده")
                        markup = self.keyboard(host, engine_id)
                        if query.message is not None:
                            await query.message.reply_text(text, reply_markup=markup)
                        return
                    text = self.detail(host, engine_id)
                    markup = self.keyboard(host, engine_id)
        except (LocalCustomRefused, AdminCustomPanelRefused, ValueError):
            if query.message is not None:
                await query.message.reply_text(
                    "⚠️ وضعیت تغییر کرده یا عملیات مجاز نیست. صفحه را تازه کنید.")
            return
        if query.message is not None:
            await query.message.reply_text(text, reply_markup=markup)

    async def route_input(self, update, context) -> None:
        if not _private_admin(update, self.admin_ids):
            return
        pending = context.user_data.get(_PENDING)
        if pending is None:
            return
        context.user_data.pop(_PENDING, None)
        message = update.effective_message
        if message is None or not message.text:
            return
        engine_id, expected_revision, actor_id = pending
        text = message.text.strip()
        # Numeric private channel only; @username is PUBLIC and is rejected.
        if (not re.fullmatch(r"-100[0-9]{6,16}", text)
                or actor_id != update.effective_user.id):
            await message.reply_text("⚠️ فقط شناسه عددی کانال خصوصی مجاز است.")
            return
        try:
            channel_id = int(text)
            chat = await context.bot.get_chat(channel_id)
            me = await context.bot.get_me()
            member = await context.bot.get_chat_member(channel_id, me.id)
            if (getattr(chat, "type", None) != "channel"
                    or getattr(chat, "username", None)
                    or getattr(member, "status", None) not in (
                        "administrator", "creator")
                    or (member.status == "administrator"
                        and getattr(member, "can_post_messages", False) is not True)):
                raise AdminCustomPanelRefused("CUSTOM_PRIVATE_CHANNEL_NOT_VERIFIED")
            with self._open() as host:
                state = host.get(engine_id)
                if state is None or state.revision != expected_revision:
                    raise AdminCustomPanelRefused("CUSTOM_PENDING_REVISION_CHANGED")
                host.set_route(
                    engine_id, channel_id=channel_id,
                    channel_title=_safe_title(getattr(chat, "title", "") or ""),
                    actor_id=actor_id, verified_private_channel=True)
                detail = self.detail(host, engine_id)
                keyboard = self.keyboard(host, engine_id)
            await message.reply_text(
                "✅ مقصد ذخیره شد. ارسال خودکار همچنان غیرفعال است.\n\n"
                + detail, reply_markup=keyboard)
        except (LocalCustomRefused, AdminCustomPanelRefused, ValueError, OSError):
            await message.reply_text(
                "⚠️ کانال قابل تأیید نیست یا وضعیت هسته تغییر کرده است.")
        except Exception:
            # Telegram network errors are never echoed (may leak token/URL).
            await message.reply_text(
                "⚠️ ارتباط با تلگرام یا بررسی مجوز ارسال ناموفق بود.")

    def register(self, application) -> None:
        """Mount in an existing Application once, AFTER legacy handlers.

        This does NOT modify the frozen legacy application, inject a second
        poller, start a network connection or deploy to production.
        """
        from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters
        private = filters.ChatType.PRIVATE
        application.add_handler(
            CommandHandler("custom", self.panel, filters=private), group=0)
        application.add_handler(
            MessageHandler(private & filters.Regex(rf"^{re.escape(MENU_LABEL)}$"),
                           self.panel), group=0)
        application.add_handler(
            CallbackQueryHandler(self.callback, pattern=r"^cm:"), group=0)
        # The generic text receiver is group 1, so normal existing admin
        # routes retain precedence. It is inert without a pending route.
        application.add_handler(
            MessageHandler(private & filters.TEXT & ~filters.COMMAND,
                           self.route_input), group=1)
