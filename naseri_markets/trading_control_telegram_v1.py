"""Opt-in Stage-12 Telegram UI; no polling, orders, market APIs or publishers.

Register with the *existing development* python-telegram-bot Application.
Command and callbacks are private-chat only and scoped to verified admin IDs.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from .trading_control_center_v1 import ControlRefused, OfflineTradingControlCenter

_ACTION = re.compile(r"t12:(list|open|toggle):?(\d{1,12}|an|sg|pp)?(?::(\d{1,12}))?(?::(\d{1,12}))?\Z")


class TelegramControlPreviewPanel:
    """Offline manager. Receives only attested framework Update objects."""

    def __init__(self, center: OfflineTradingControlCenter):
        if not isinstance(center, OfflineTradingControlCenter):
            raise ControlRefused("CONTROL_CENTER_REQUIRED")
        self.center = center

    @staticmethod
    def _actor(update):
        user = getattr(update, "effective_user", None)
        chat = getattr(update, "effective_chat", None)
        ident = getattr(user, "id", None)
        if (type(ident) is not int or ident <= 0
                or getattr(chat, "type", None) != "private"
                or getattr(chat, "id", None) != ident):
            raise ControlRefused("PRIVATE_USER_CONTEXT_REQUIRED")
        query = getattr(update, "callback_query", None)
        if query is not None and getattr(getattr(query, "from_user", None),"id",None) != ident:
            raise ControlRefused("CALLBACK_ACTOR_MISMATCH")
        return ident

    @staticmethod
    def _kb(rows):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(label, callback_data=cb) for label,cb in row]
            for row in rows
        ])

    def _overview(self, actor):
        listings = self.center.available_cores(actor)
        instances = self.center.instances(actor)
        byname = ", ".join(item.name for item in listings)
        body = ("🎛 مرکز مدیریت هسته‌ها — NONPRODUCTION\n"
                "فقط تنظیمات پژوهشی؛ بدون ارسال تلگرام و سفارش واقعی.\n"
                f"هسته‌های مجاز: {byname}\n"
                f"نمونه‌های شما: {len(instances)}\n"
                "ساخت: /mmt12_new CORE_ID INSTANCE_ID ACCOUNT_ID PORTFOLIO_ID\n"
                "نماد: /mmt12_add INSTANCE_ID PROVIDER SYMBOL TIMEFRAME\n"
                "سرمایه: /mmt12_risk INSTANCE_ID RESERVED NOTIONAL ORDER MAX_ORDERS\n"
                "حذف نماد: /mmt12_del INSTANCE_ID BINDING_ID\n"
                "پارامترها: /mmt12_params INSTANCE_ID\n"
                "ثبت تنظیمات کامل: /mmt12_param_set INSTANCE_ID REV JSON\n"
                "TIMEFRAME: 1m 5m 15m 30m 1h 4h 12h 1d\n"
                "LIVE: 🔒 همیشه خاموش | سیگنال واقعی: 🔒 خاموش")
        rows=[]
        for s in instances[:30]:
            ident = self.center._db.execute("SELECT rowid FROM t12_instances WHERE instance_id=?",(s.instance_id,)).fetchone()[0]
            rows.append([(s.instance_id[:32],f"t12:open:{ident}")])
        if not rows:
            rows = [[("↻ بروزرسانی","t12:list")]]
        return body, self._kb(rows)

    def _detail(self, actor, ident):
        s=self.center.inspect(actor,ident)
        bindings=self.center.bindings(actor,ident)
        lines=[f"🔧 {s.core_name} | {s.instance_id}",
               f"حساب: {s.account_id} | سبد: {s.portfolio_id}",
               f"نسخه تنظیمات: {s.revision} | مسیرها: {len(bindings)}",
               f"تحلیل آزمایشی (درخواست): {'ON' if s.analysis_requested else 'OFF'}",
               f"سیگنال آزمایشی (درخواست): {'ON' if s.telegram_signals_requested else 'OFF'}",
               f"سفارش PAPER (درخواست): {'ON' if s.paper_orders_requested else 'OFF'}",
               f"حداکثر ریسک هسته: {s.max_reserved_risk_fraction}",
               f"حداکثر ریسک سفارش: {s.max_order_risk_fraction}",
               f"حداکثر Notional: {s.max_notional_fraction}",
               "🔒 انتشار واقعی، معاملات و LIVE: غیرفعال"]
        params = self.center.inspect_core_parameters(actor, ident)
        lines.append(f"پارامترها: {params['status']} ({params['count']})")
        if params["settings_sha256"]:
            lines.append("اثر انگشت تنظیمات: " + params["settings_sha256"][:16])
        lines += [f"• {v.provider}:{v.symbol} [{v.market}] {v.timeframe} ({v.binding_id})" for v in bindings[:12]]
        rowid=self.center._db.execute("SELECT rowid FROM t12_instances WHERE instance_id=?",(ident,)).fetchone()[0]
        rows=[]
        for k, title in (("an","تحلیل"),("sg","سیگنال آزمایشی"),("pp","سفارش PAPER آزمایشی")):
            rows.append([(f"تغییر درخواست {title}",f"t12:toggle:{k}:{rowid}:{s.revision}")])
        rows.append([("↩ فهرست","t12:list")])
        return "\n".join(lines),self._kb(rows)

    def _instance_from_rowid(self, actor, rowid):
        if type(rowid) is not int or rowid <= 0:
            raise ControlRefused("INVALID_INSTANCE_SELECTOR")
        row=self.center._db.execute("SELECT instance_id FROM t12_instances WHERE rowid=?",(rowid,)).fetchone()
        if row is None:
            raise ControlRefused("INSTANCE_NOT_ACCESSIBLE")
        self.center.inspect(actor,row["instance_id"])
        return row["instance_id"]

    async def command(self, update, context):
        try:
            actor=self._actor(update)
            self.center._auth(actor)
            raw=getattr(getattr(update,"effective_message",None),"text","") or ""
            parts=raw.split()
            command=parts[0].split("@",1)[0] if parts else ""
            args=parts[1:]
            if command == "/mmt12":
                text,markup=self._overview(actor)
            elif command == "/mmt12_new" and len(args)==4:
                self.center.create_instance(actor,core_id=args[0],instance_id=args[1],account_id=args[2],portfolio_id=args[3])
                text,markup=self._detail(actor,args[1])
            elif command == "/mmt12_add" and len(args)==4:
                rev=self.center.inspect(actor,args[0]).revision
                self.center.add_binding(actor,args[0],provider=args[1],symbol=args[2],timeframe=args[3],
                                        now=datetime.now(UTC),expected_revision=rev)
                text,markup=self._detail(actor,args[0])
            elif command == "/mmt12_del" and len(args)==2:
                rev=self.center.inspect(actor,args[0]).revision
                self.center.remove_binding(actor,args[0],binding_id=args[1],expected_revision=rev)
                text,markup=self._detail(actor,args[0])
            elif command == "/mmt12_params" and len(args)==1:
                s = self.center.inspect(actor, args[0])
                info = self.center.inspect_core_parameters(actor, args[0])
                listing = self.center._listing(actor, s.core_id)
                names = ()
                if listing.parameter_schema_bytes is not None:
                    # Host-reviewed JSON is data, never evaluated as Python.
                    schema = json.loads(listing.parameter_schema_bytes)
                    names = tuple(
                        f"{p['name']} ({p['kind']})"
                        for p in schema["parameters"]
                    )
                text = ("پارامترهای مجاز پژوهشی — اجرای معاملات غیرفعال\n"
                        f"وضعیت: {info['status']}\n"
                        f"نسخه: {s.revision}\n"
                        f"اثر انگشت: {info['settings_sha256'] or 'unset'}\n"
                        + "\n".join(names))
                markup = None
            elif command == "/mmt12_param_set":
                # Entire versioned Stage-6 settings envelope is required.
                # Do not echo submitted values, even when validation fails.
                pieces = raw.split(maxsplit=3)
                if len(pieces) != 4 or len(raw.encode("utf-8")) > 4096:
                    raise ControlRefused("INVALID_PARAMETER_COMMAND")
                try:
                    revision = int(pieces[2])
                    if str(revision) != pieces[2]:
                        raise ValueError
                except ValueError as exc:
                    raise ControlRefused("INVALID_PARAMETER_REVISION") from exc
                self.center.set_core_parameters(
                    actor, pieces[1], settings_bytes=pieces[3].encode("utf-8"),
                    expected_revision=revision,
                )
                text, markup = self._detail(actor, pieces[1])
            elif command == "/mmt12_risk" and len(args)==5:
                rev=self.center.inspect(actor,args[0]).revision
                # Reject floats and malformed Decimal syntax; never guess units.
                try:
                    risk,notional,order=(Decimal(v) for v in args[1:4])
                    max_orders=int(args[4])
                    if any("e" in v.lower() for v in args[1:4]) or args[4].startswith(("+","-")):
                        raise ValueError
                except (InvalidOperation,ValueError) as exc:
                    raise ControlRefused("INVALID_ALLOCATION_INPUT") from exc
                self.center.set_allocation(actor,args[0],max_reserved=risk,max_notional=notional,
                                           max_order=order,max_orders=max_orders,expected_revision=rev)
                text,markup=self._detail(actor,args[0])
            else:
                raise ControlRefused("INVALID_PANEL_COMMAND")
        except ControlRefused:
            text,markup="⚠️ درخواست نامعتبر، غیرمجاز یا اطلاعات بازار تأییدنشده است.",None
        msg=getattr(update,"effective_message",None)
        if msg is not None:
            await msg.reply_text(text,reply_markup=markup)

    async def callback(self, update, context):
        query=getattr(update,"callback_query",None)
        if query is None:
            return
        try:
            actor=self._actor(update)
            self.center._auth(actor)
            raw=getattr(query,"data",None)
            if type(raw) is not str or len(raw.encode("utf-8"))>64:
                raise ControlRefused("INVALID_CALLBACK")
            if raw=="t12:list":
                text,markup=self._overview(actor)
            else:
                m=_ACTION.fullmatch(raw)
                if m is None:
                    raise ControlRefused("INVALID_CALLBACK")
                if m.group(1)=="open" and m.group(2) is not None and m.group(3) is None:
                    ident=self._instance_from_rowid(actor,int(m.group(2)))
                elif m.group(1)=="toggle" and m.group(2) in ("an","sg","pp") and m.group(3) and m.group(4):
                    ident=self._instance_from_rowid(actor,int(m.group(3)))
                    s=self.center.inspect(actor,ident)
                    field={"an":"analysis","sg":"signals","pp":"paper"}[m.group(2)]
                    old={"analysis":s.analysis_requested,"signals":s.telegram_signals_requested,
                         "paper":s.paper_orders_requested}[field]
                    self.center.set_request(actor,ident,field=field,requested=not old,
                                            expected_revision=int(m.group(4)))
                else:
                    raise ControlRefused("INVALID_CALLBACK")
                text,markup=self._detail(actor,ident)
            await query.answer()
        except ControlRefused:
            await query.answer("تنظیمات قدیمی یا دسترسی نامعتبر است",show_alert=True)
            return
        if getattr(query,"message",None) is not None:
            await query.message.reply_text(text,reply_markup=markup)

    def register(self, application) -> None:
        """Only mounts handlers; never calls Application.run_polling()."""
        from telegram.ext import CommandHandler, CallbackQueryHandler
        for command in ("mmt12","mmt12_new","mmt12_add","mmt12_del","mmt12_risk",
                        "mmt12_params","mmt12_param_set"):
            application.add_handler(CommandHandler(command,self.command))
        application.add_handler(CallbackQueryHandler(self.callback,pattern=r"^t12:"))


__all__=["TelegramControlPreviewPanel"]
