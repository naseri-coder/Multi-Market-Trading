"""Integrated NON-PRODUCTION bot engine manager.

Brooks is visible as a built-in reference; owner Custom is owner-visible
only when explicitly provisioned in local private inventory. Both are
configuration-only until their *own* runtime adapters are authorized.
Real trusted public Custom PAPER can be enabled/disabled. No Telegram
signal channel posting, live trade or private core package execution.
"""
from __future__ import annotations

import re
from pathlib import Path

from .custom_admin_panel import (
    AdminCustomPanelRefused, CustomAdminPanel, _private_admin,
    _resolve, _safe_title, _token,
)
from .engine_control_store import (
    BROOKS_ENGINE_ID, OWNER_CORE_ID, EngineControlStore, MARKET_SCOPES, TIMEFRAMES,
)
from .futures_venues import (
    FUTURES_VENUES, get_venue, paper_feed_verified,
    iran_status_text, feed_status_text,
)
from .futures_pairs import pair_choices, pair_is_verified_paper
from .trusted_custom import LocalCustomRefused

_MORE = re.compile(r"em:(settings|tf|market|env):([0-9a-f]{12})(?::([0-9]+))?\Z")
_EXCHANGE = re.compile(r"ex:(list|set):([0-9a-f]{12}):([0-9]+)(?::([0-9]+))?\Z")
_TF = re.compile(r"et:(list|set):([0-9a-f]{12})(?::([0-9]+))?(?::([0-9]+))?\Z")
_PAIR = re.compile(r"ep:(list|set):([0-9a-f]{12})(?::([0-9]+))?(?::([0-9]+))?\Z")
_PAGE_SIZE = 5


class IntegratedEnginePanel(CustomAdminPanel):
    """The next-generation same-Application Telegram panel; no new poller."""

    def __init__(self, *, state_dir: str | Path, admin_ids,
                 owner_ids=()):
        super().__init__(state_dir=state_dir, admin_ids=admin_ids)
        owners = frozenset(owner_ids)
        if any(type(x) is not int or x not in self.admin_ids for x in owners):
            raise AdminCustomPanelRefused("ENGINE_OWNER_MUST_BE_EXPLICIT_ADMIN")
        object.__setattr__(self, "owner_ids", owners)

    def _open(self, actor_id: int | None = None) -> EngineControlStore:
        return EngineControlStore(
            self.state_dir, owner_visible=actor_id in self.owner_ids)

    def keyboard(self, host: EngineControlStore, selected: str | None = None):
        from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup
        if selected is None:
            rows = []
            for engine in host.list()[:30]:
                worker = (host.brooks_worker_status()
                          if engine.engine_kind == "BUILTIN_BROOKS" else None)
                if worker is not None and worker["connected"]:
                    armed_feed = paper_feed_verified(
                        host.preferences(engine.engine_id)["futures_exchange"])
                    armed_feed = armed_feed and pair_is_verified_paper(
                        host.preferences(engine.engine_id)["futures_exchange"],
                        host.preferences(engine.engine_id)["futures_symbol"])
                    badge = "🟢" if engine.requested_enabled and armed_feed else "⏸"
                elif engine.runtime_status == "RUNTIME_NOT_MOUNTED":
                    badge = "🟡" if engine.requested_enabled else "🔒"
                else:
                    badge = "✅" if engine.enabled else "⏸"
                label = (
                    "📚 پرایس اکشن البروکس (Brooks)"
                    if engine.engine_kind == "BUILTIN_BROOKS" else
                    "🔐 NY First-Reversal — Custom اختصاصی"
                    if engine.engine_kind == "OWNER_CUSTOM" else engine.engine_id
                )
                rows.append([Button(f"{badge} {label}",
                                    callback_data=f"cm:open:{_token(engine.engine_id)}")])
            rows.append([Button("🔄 تازه‌سازی", callback_data="cm:list")])
            return InlineKeyboardMarkup(rows)
        state = host.get(selected)
        if state is None:
            raise AdminCustomPanelRefused("ENGINE_UNKNOWN_OR_PRIVATE")
        idtoken = _token(selected)
        requested = state.requested_enabled
        worker = (host.brooks_worker_status()
                  if state.engine_kind == "BUILTIN_BROOKS" else None)
        rows = [[Button(
            ("⏸ توقف تحلیل PAPER" if requested else "✅ روشن کردن تحلیل PAPER")
            if worker is not None and worker["connected"] else
            ("⏸ غیرفعال‌سازی" if requested else "✅ درخواست فعال‌سازی")
            if state.runtime_status == "RUNTIME_NOT_MOUNTED" else
            ("⏸ غیرفعال‌سازی PAPER" if requested else "✅ فعال‌سازی PAPER"),
            callback_data=f"cm:{'disable' if requested else 'enable'}:"
                          f"{idtoken}:{state.revision}")]]
        if state.engine_kind == "BUILTIN_BROOKS":
            pub = host.publication(selected)
            rows.append([Button(
                "📡 لغو درخواست انتشار" if pub["requested_publication"]
                else "📡 درخواست فعال‌سازی انتشار",
                callback_data=f"bp:{'off' if pub['requested_publication'] else 'on'}:"
                              f"{idtoken}:{pub['revision']}")])
        rows.append([Button("⚙️ تنظیمات هسته",
                            callback_data=f"em:settings:{idtoken}"),
                     Button("📤 مقصد کانال", callback_data=f"cm:route:{idtoken}")])
        rows.append([Button("🗑 حذف مقصد", callback_data=f"cm:clear:{idtoken}"),
                     Button("🧾 سیگنال PAPER", callback_data=f"cm:paper:{idtoken}")])
        rows.append([Button("📋 تاریخچه", callback_data=f"cm:audit:{idtoken}"),
                     Button("🔙 فهرست", callback_data="cm:list")])
        return InlineKeyboardMarkup(rows)

    def summary(self, host: EngineControlStore) -> str:
        items = host.list()
        worker = host.brooks_worker_status()
        brooks = next(
            (x for x in items if x.engine_kind == "BUILTIN_BROOKS"), None)
        prefs = host.preferences(brooks.engine_id) if brooks else None
        paper_armed = bool(
            brooks and brooks.requested_enabled and prefs
            and prefs["signal_environment"] == "PAPER"
            and prefs["market_scope"] in ("all", "crypto")
            and paper_feed_verified(prefs["futures_exchange"])
            and pair_is_verified_paper(
                prefs["futures_exchange"], prefs["futures_symbol"]))
        paper_active = bool(
            paper_armed and worker["connected"]
            and worker["phase"] in ("WAITING", "ANALYZING"))
        active = sum(x.enabled for x in items) + int(paper_active)
        pending = (
            sum(x.requested_enabled and not x.enabled for x in items)
            - int(paper_active))
        worker_line = (
            "🟢 سرویس مستقل Brooks: " + worker["phase"] + "\n"
            if worker["connected"] else
            "⚪ سرویس مستقل Brooks: " + worker["phase"] + "\n")
        owner_line = ("🔐 مرجع Custom خصوصی مالک، بدون اجرای کد.\n"
                      if host.owner_visible and host.get(OWNER_CORE_ID) is not None
                      else "")
        return (
            "🎛 مدیریت یکپارچه هسته‌های Multi Market Trading\n"
            f"هسته‌های قابل مشاهده: {len(items)} | PAPER فعال واقعی: {active}\n"
            f"درخواست فعال، فاقد اتصال موتور: {pending}\n"
            "پرایس اکشن البروکس: تحلیل PAPER با سرویس مستقل اختیاری.\n"
            + worker_line + owner_line +
            "کانال‌ها تنها تنظیم می‌شوند؛ ارسال خودکار: 🔒 خاموش.")

    def detail(self, host: EngineControlStore, engine_id: str) -> str:
        state = host.get(engine_id)
        if state is None:
            raise AdminCustomPanelRefused("ENGINE_UNKNOWN_OR_PRIVATE")
        prefs = host.preferences(engine_id)
        route = host.route(engine_id)
        if state.engine_kind == "BUILTIN_BROOKS":
            label = "📚 پرایس اکشن البروکس | داخلی"
        elif state.engine_kind == "OWNER_CUSTOM":
            label = "🔐 Custom مالک | خصوصی"
        else:
            label = "🔌 Custom عمومی مورداعتماد"
        worker = (host.brooks_worker_status()
                  if state.engine_kind == "BUILTIN_BROOKS" else None)
        if worker is not None and worker["connected"]:
            status = ("🟢 تحلیل PAPER آماده/درحال اجرا"
                      if state.requested_enabled and
                      prefs["signal_environment"] == "PAPER"
                      and paper_feed_verified(prefs["futures_exchange"])
                      and pair_is_verified_paper(
                          prefs["futures_exchange"], prefs["futures_symbol"]) else
                      "⏸ سرویس حاضر است؛ تحلیل از پنل خاموش است")
        elif state.runtime_status == "RUNTIME_NOT_MOUNTED":
            status = ("🟡 درخواست فعال‌سازی ثبت شده" if state.requested_enabled
                      else "⏸ درخواست اجرا غیرفعال")
            status += " — هسته واقعی هنوز متصل نیست"
        else:
            status = "✅ PAPER فعال" if state.enabled else "⏸ PAPER غیرفعال"
        publication_line = ""
        if state.engine_kind == "BUILTIN_BROOKS":
            publication = host.publication(engine_id)
            publication_line = (
                "درخواست انتشار سیگنال: "
                + ("✅ ثبت شده" if publication["requested_publication"] else "⏸ ثبت نشده")
                + "\nانتشار مؤثر سیگنال: 🔒 غیرفعال (ناشر کانال وجود ندارد)\n"
            )
        replay_line = ""
        if state.engine_kind == "BUILTIN_BROOKS":
            replay = host.brooks_replay_status()
            replay_line = (
                f"اسکن‌های واقعی Replay: {replay['scans']}\n"
                f"اسکن‌های بدون سیگنال: {replay['no_signal']}\n"
                f"سرویس Futures PAPER: {worker['phase']}\n"
                f"آخرین کندل: {worker['last_closed_candle'] or 'ثبت نشده'}\n"
                f"چرخه‌های موفق: {worker['completed_cycles']} | "
                f"خطاهای کنترل‌شده: {worker['refused_cycles']}\n"
                f"آخرین خطا: {worker['last_error'] or 'ندارد'}\n"
                "کنترل روشن/خاموش از پنل مؤثر است؛ آغاز فرایند مستقل "
                "فقط با اجرای صریح در محیط توسعه.\n"
            )
        return (
            f"{label}\nشناسه: {engine_id}\n"
            f"وضعیت: {status}\nنسخه تنظیمات هسته: {state.revision}\n"
            f"صرافی فیوچرز: {get_venue(prefs['futures_exchange']).name if worker is not None else '—'}\n"
            f"آمادگی فید: {feed_status_text(prefs['futures_exchange']) if worker is not None else '—'}\n"
            f"دسترسی کاربران ایران: {iran_status_text(prefs['futures_exchange']) if worker is not None else '—'}\n"
            f"جفت‌ارز فیوچرز: {prefs['futures_symbol'] if worker is not None else '—'}\n"
            f"بازه زمانی انتخابی: {prefs['timeframe']} "
            f"({'مؤثر بر سرویس PAPER مستقل' if worker is not None else 'تنظیم'})\n"
            f"بازار انتخابی: {prefs['market_scope']}\n"
            f"محیط سیگنال: {prefs['signal_environment']} (بدون LIVE)\n"
            f"مقصد: {_safe_title(route['channel_title']) if route['channel_id'] else 'ثبت نشده'}\n"
            f"انتشار به کانال: 🔒 DISABLED\n"
            f"{publication_line}"
            f"{replay_line}"
            f"سیگنال‌های PAPER: {len(host.signals(engine_id))}\n"
            "تغییرات تنها بر همین هسته اعمال می‌شوند.")

    def settings_text(self, host: EngineControlStore, engine_id: str) -> str:
        preferences = host.preferences(engine_id)
        venue_line = ""
        if engine_id == BROOKS_ENGINE_ID:
            venue = get_venue(preferences["futures_exchange"])
            venue_line = (
                f"صرافی فیوچرز: {venue.name}\n"
                f"جفت‌ارز فیوچرز: {preferences['futures_symbol']}\n"
                + ("🧪 این قرارداد قابلیت تحلیل PAPER دارد.\n"
                   if pair_is_verified_paper(
                       preferences["futures_exchange"],
                       preferences["futures_symbol"])
                   else "⚪ این نماد صرفاً نامزد است؛ فید PAPER فعال نیست.\n") +
                f"وضعیت فید: {feed_status_text(venue.key)}\n"
                f"وضعیت ایران: {iran_status_text(venue.key)}\n"
                "⚠️ وجود صرافی در فهرست به‌معنای مجاز بودن برای ایران نیست.\n"
                "فقط صرافی با فید اعتبارسنجی‌شده قابلیت تحلیل PAPER دارد.\n")
        return (f"⚙️ تنظیمات {engine_id}\n"
                + venue_line +
                f"تایم‌فریم: {preferences['timeframe']} "
                f"({'مؤثر در سرویس مستقل PAPER' if engine_id == 'brooks_price_action' else 'اطلاعاتی'})\n"
                f"بازار: {preferences['market_scope']}\n"
                f"محیط: {preferences['signal_environment']}\n"
                f"نسخه تنظیمات: {preferences['revision']}\n"
                "اجرای LIVE و ارسال خودکار کانال مجاز نیست.")

    def settings_keyboard(self, host: EngineControlStore, engine_id: str):
        from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup
        prefs = host.preferences(engine_id)
        token = _token(engine_id)
        revision = prefs["revision"]
        options = [
            [Button("⏱ انتخاب تایم‌فریم",
                    callback_data=f"et:list:{token}")] if engine_id == BROOKS_ENGINE_ID
            else [Button("⏱ تغییر تایم‌فریم",
                         callback_data=f"em:tf:{token}:{revision}")],
            *([[Button("🏦 انتخاب صرافی فیوچرز (۲۰ مورد)",
                       callback_data=f"ex:list:{token}:0")],
               [Button("💱 انتخاب جفت‌ارز فیوچرز",
                       callback_data=f"ep:list:{token}")]]
              if engine_id == BROOKS_ENGINE_ID else []),
            [Button("🌍 تغییر بازار",
                    callback_data=f"em:market:{token}:{revision}")],
            [Button("🧪 PAPER / خاموش",
                    callback_data=f"em:env:{token}:{revision}")],
            [Button("🔙 بازگشت به هسته", callback_data=f"cm:open:{token}")],
        ]
        return InlineKeyboardMarkup(options)

    def exchange_keyboard(self, host: EngineControlStore, engine_id: str,
                          page: int):
        """Paged stable allowlist; Telegram callback payloads stay <64 bytes."""
        from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup
        if engine_id != BROOKS_ENGINE_ID or not 0 <= page < 4:
            raise AdminCustomPanelRefused("BROOKS_EXCHANGE_PAGE_DENIED")
        prefs = host.preferences(engine_id)
        token = _token(engine_id)
        start = page * _PAGE_SIZE
        rows = []
        for index in range(start, min(start + _PAGE_SIZE, len(FUTURES_VENUES))):
            venue = FUTURES_VENUES[index]
            flag = ("⛔" if venue.iran_access == "EXPLICIT_RESTRICTION"
                    else "🧪" if paper_feed_verified(venue.key) else "⚪")
            selected = "✅" if venue.key == prefs["futures_exchange"] else ""
            rows.append([Button(
                f"{selected}{flag} {venue.name}",
                callback_data=f"ex:set:{token}:{index}:{prefs['revision']}")])
        nav = []
        if page:
            nav.append(Button("◀ قبلی", callback_data=f"ex:list:{token}:{page-1}"))
        if page < 3:
            nav.append(Button("بعدی ▶", callback_data=f"ex:list:{token}:{page+1}"))
        if nav:
            rows.append(nav)
        rows.append([Button("🔙 تنظیمات", callback_data=f"em:settings:{token}")])
        return InlineKeyboardMarkup(rows)

    def timeframe_keyboard(self, host: EngineControlStore, engine_id: str):
        from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup
        if engine_id != BROOKS_ENGINE_ID:
            raise AdminCustomPanelRefused("BROOKS_TIMEFRAME_ONLY")
        prefs = host.preferences(engine_id)
        token = _token(engine_id)
        names = {
            "1m": "۱ دقیقه", "5m": "۵ دقیقه", "15m": "۱۵ دقیقه",
            "30m": "۳۰ دقیقه", "1h": "۱ ساعت", "4h": "۴ ساعت",
            "12h": "۱۲ ساعت", "1d": "روزانه",
        }
        rows = []
        for index in range(0, len(TIMEFRAMES), 2):
            rows.append([
                Button(("✅ " if prefs["timeframe"] == TIMEFRAMES[j] else "")
                       + names[TIMEFRAMES[j]],
                       callback_data=f"et:set:{token}:{j}:{prefs['revision']}")
                for j in range(index, index + 2)])
        rows.append([Button("🔙 تنظیمات", callback_data=f"em:settings:{token}")])
        return InlineKeyboardMarkup(rows)

    def pair_keyboard(self, host: EngineControlStore, engine_id: str):
        """Pairs are scoped to the saved venue; no spot symbols or free text."""
        from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup
        if engine_id != BROOKS_ENGINE_ID:
            raise AdminCustomPanelRefused("BROOKS_PAIR_SELECTION_DENIED")
        pref = host.preferences(engine_id)
        options = pair_choices(pref["futures_exchange"])
        token = _token(engine_id)
        rows = []
        for idx in range(0, len(options), 2):
            row = []
            for index in range(idx, min(idx + 2, len(options))):
                pair = options[index]
                current = "✅ " if pref["futures_symbol"] == pair else ""
                status = ("🧪 " if pair_is_verified_paper(
                    pref["futures_exchange"], pair) else "⚪ ")
                row.append(Button(
                    current + status + pair,
                    callback_data=f"ep:set:{token}:{index}:{pref['revision']}"))
            rows.append(row)
        rows.append([Button("🔙 تنظیمات", callback_data=f"em:settings:{token}")])
        return InlineKeyboardMarkup(rows)

    async def callback(self, update, context) -> None:
        query = getattr(update, "callback_query", None)
        if query is None:
            return
        if (query.data or "").startswith(("ex:", "et:", "ep:")):
            if not _private_admin(update, self.admin_ids):
                await query.answer("دسترسی مجاز نیست", show_alert=True)
                return
            is_exchange = (query.data or "").startswith("ex:")
            is_pair = (query.data or "").startswith("ep:")
            match = (_EXCHANGE if is_exchange else
                     _PAIR if is_pair else _TF).fullmatch(
                query.data or "")
            if match is None:
                await query.answer("درخواست نامعتبر", show_alert=True)
                return
            await query.answer()
            try:
                with self._open(update.effective_user.id) as host:
                    state = _resolve(host, match.group(2))
                    if state.engine_id != BROOKS_ENGINE_ID:
                        raise LocalCustomRefused("BROOKS_SETTING_ONLY")
                    prefs = host.preferences(BROOKS_ENGINE_ID)
                    if match.group(1) == "set":
                        if match.group(4) is None or (
                                int(match.group(4)) != prefs["revision"]):
                            raise LocalCustomRefused("ENGINE_STALE_SETTING_REVISION")
                        choices = (
                            FUTURES_VENUES if is_exchange else
                            pair_choices(prefs["futures_exchange"]) if is_pair
                            else TIMEFRAMES)
                        index = int(match.group(3))
                        if not 0 <= index < len(choices):
                            raise LocalCustomRefused("ENGINE_CHOICE_OUT_OF_BOUNDS")
                        value = (choices[index].key if is_exchange
                                 else choices[index])
                        host.change_preference(
                            state.engine_id,
                            field=("futures_exchange" if is_exchange
                                   else "futures_symbol" if is_pair
                                   else "timeframe"),
                            value=value, expected_revision=prefs["revision"],
                            actor_id=update.effective_user.id)
                    if is_exchange:
                        page = (int(match.group(3)) // _PAGE_SIZE
                                if match.group(1) == "set"
                                else int(match.group(3)))
                        markup = self.exchange_keyboard(host, state.engine_id, page)
                        message = (
                            f"🏦 صرافی انتخاب‌شده: "
                            f"{get_venue(host.preferences(state.engine_id)['futures_exchange']).name}\n"
                            "⛔ = ایران رسماً محدود | ⚪ = دسترسی ایران نامشخص\n"
                            "این فهرست تضمین دسترسی قانونی یا فید آماده نیست.")
                    elif is_pair:
                        markup = self.pair_keyboard(host, state.engine_id)
                        current = host.preferences(state.engine_id)
                        message = (
                            f"💱 جفت‌ارز انتخاب‌شده: {current['futures_symbol']}\n"
                            f"صرافی: {get_venue(current['futures_exchange']).name}\n"
                            "🧪=تحلیل PAPER معتبر | ⚪=صرفاً نامزد؛ بدون فید\n"
                            "ثبت نماد به‌تنهایی به معنی صدور سیگنال نیست.")
                    else:
                        markup = self.timeframe_keyboard(host, state.engine_id)
                        message = (
                            f"⏱ تایم‌فریم: {host.preferences(state.engine_id)['timeframe']}\n"
                            "هشت دوره استاندارد؛ هر تغییر، تنظیمات تحلیل PAPER را به‌روزرسانی می‌کند.")
                if query.message is not None:
                    await query.message.reply_text(message, reply_markup=markup)
            except (LocalCustomRefused, AdminCustomPanelRefused, ValueError):
                if query.message is not None:
                    await query.message.reply_text("⚠️ انتخاب نامعتبر یا قدیمی است؛ تنظیمات را تازه کنید.")
            return
        if (query.data or "").startswith("bp:"):
            if not _private_admin(update, self.admin_ids):
                await query.answer("دسترسی مجاز نیست", show_alert=True)
                return
            match = re.fullmatch(r"bp:(on|off):([0-9a-f]{12}):([0-9]+)",
                                 query.data or "")
            if match is None:
                await query.answer("درخواست نامعتبر", show_alert=True)
                return
            await query.answer()
            try:
                with self._open(update.effective_user.id) as host:
                    state = _resolve(host, match.group(2))
                    if state.engine_kind != "BUILTIN_BROOKS":
                        raise LocalCustomRefused("ENGINE_PUBLICATION_PERMISSION_DENIED")
                    host.request_publication(
                        state.engine_id, enabled=match.group(1) == "on",
                        expected_revision=int(match.group(3)),
                        actor_id=update.effective_user.id)
                    response = self.detail(host, state.engine_id)
                    markup = self.keyboard(host, state.engine_id)
                if query.message is not None:
                    await query.message.reply_text(response, reply_markup=markup)
            except (LocalCustomRefused, AdminCustomPanelRefused):
                if query.message is not None:
                    await query.message.reply_text("⚠️ درخواست قدیمی یا غیرمجاز است.")
            return
        if not (query.data or "").startswith("em:"):
            await super().callback(update, context)
            return
        if not _private_admin(update, self.admin_ids):
            await query.answer("دسترسی مجاز نیست", show_alert=True)
            return
        parsed = _MORE.fullmatch(query.data or "")
        if parsed is None:
            await query.answer("عملیات نامعتبر", show_alert=True)
            return
        action, token, supplied_revision = parsed.groups()
        await query.answer()
        try:
            with self._open(update.effective_user.id) as host:
                state = _resolve(host, token)
                prefs = host.preferences(state.engine_id)
                if action != "settings":
                    if supplied_revision is None or int(supplied_revision) != prefs["revision"]:
                        raise LocalCustomRefused("ENGINE_STALE_SETTING_REVISION")
                    if action == "tf":
                        field, choices = "timeframe", TIMEFRAMES
                    elif action == "market":
                        field, choices = "market_scope", MARKET_SCOPES
                    else:
                        field, choices = "signal_environment", ("OFF", "PAPER")
                    current = prefs[field]
                    target = choices[(choices.index(current) + 1) % len(choices)]
                    host.change_preference(
                        state.engine_id, field=field, value=target,
                        expected_revision=prefs["revision"],
                        actor_id=update.effective_user.id)
                message = self.settings_text(host, state.engine_id)
                markup = self.settings_keyboard(host, state.engine_id)
            if query.message is not None:
                await query.message.reply_text(message, reply_markup=markup)
        except (LocalCustomRefused, AdminCustomPanelRefused, ValueError):
            if query.message is not None:
                await query.message.reply_text(
                    "⚠️ مجوز، تنظیمات یا نسخه تغییر کرده است. دوباره وارد شوید.")

    def register(self, application) -> None:
        super().register(application)
        from telegram.ext import CallbackQueryHandler, CommandHandler, filters
        # The shared Custom panel registers only cm: callbacks. Explicitly
        # register the integrated settings and Brooks publication callbacks,
        # otherwise Telegram silently drops taps on their inline buttons.
        application.add_handler(
            CallbackQueryHandler(self.callback, pattern=r"^(?:em:|bp:|ex:|et:|ep:)"),
            group=0)
        application.add_handler(
            CommandHandler("engines", self.panel, filters=filters.ChatType.PRIVATE),
            group=0)
