"""R31: private offline Stage12 administrator read view + atomic disable.

Consumes existing Stage12/17/10 authorities without another settings database.
A framework Update must be authenticated by the trusted Telegram host before
an actor is accepted. PRIVATE replies are UI, never publication of signals
to channels or actual delivery receipts.
"""
from __future__ import annotations

import os
from collections import Counter

from .offline_runtime_supervisor_v1 import OfflineRuntimeSupervisor
from .offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from .trading_control_center_v1 import (
    ControlRefused, OfflineTradingControlCenter,
)


class R31AdminRefused(ValueError):
    """Sanitized refusal for untrusted commands or evidence."""


class R31OfflineAdminConsole:
    """Additive operator interface: no broker, channel transport or LIVE toggle."""

    def __init__(
        self, center: OfflineTradingControlCenter, *,
        signals: OfflineSignalLifecycle | None = None,
        supervisor: OfflineRuntimeSupervisor | None = None,
        operator_ack: bool = False,
    ) -> None:
        if (operator_ack is not True
                or type(center) is not OfflineTradingControlCenter
                or center.enabled is not True
                or (signals is not None
                    and type(signals) is not OfflineSignalLifecycle)
                or (supervisor is not None
                    and (type(supervisor) is not OfflineRuntimeSupervisor
                         or supervisor.panel is not center))):
            raise R31AdminRefused("R31_EXISTING_OFFLINE_COMPONENTS_REQUIRED")
        self.center = center
        self.signals = signals
        self.supervisor = supervisor
        self._offline()

    @staticmethod
    def _offline() -> None:
        if (os.environ.get("MMT_NONPRODUCTION") != "1"
                or os.environ.get("MMT_PRODUCTION") == "1"):
            raise R31AdminRefused("R31_NONPRODUCTION_ONLY")

    def _actor(self, actor_id: int) -> None:
        self._offline()
        self.center._auth(actor_id)
        if (self.supervisor is not None
                and self.supervisor.actor_id != actor_id):
            raise R31AdminRefused("R31_SUPERVISOR_ACTOR_MISMATCH")

    def overview(self, actor_id: int) -> dict:
        self._actor(actor_id)
        instances = self.center.instances(actor_id)
        return {
            "protocol": "MMT_R31_PRIVATE_ADMIN_OFFLINE_V1",
            "accessible_instances": tuple(s.instance_id for s in instances),
            "visible_core_references": tuple(
                c.core_id for c in self.center.available_cores(actor_id)
            ),
            "private_panel_scope": True,
            "market_data_verified_for_trading": False,
            "telegram_signal_publication_enabled": False,
            "broker_orders_enabled": False,
            "live_trading_enabled": False,
        }

    def detail(self, actor_id: int, instance_id: str) -> dict:
        self._actor(actor_id)
        state = self.center.inspect(actor_id, instance_id)
        routes = self.center.bindings(actor_id, instance_id)
        parameters = self.center.inspect_core_parameters(actor_id, instance_id)
        queue = (
            self.supervisor.health() if self.supervisor is not None else None
        )
        if queue is not None and any(queue.get(k) is not False for k in (
            "telegram_sent", "broker_order_sent", "live_trading_enabled",
            "background_poller",
        )):
            raise R31AdminRefused("R31_UNEXPECTED_RUNTIME_SIDE_EFFECT")
        unresolved = (
            queue is None
            or queue.get("manual_reconciliation_required") is not False
            or queue.get("counts", {}).get("CLAIMED", 0) != 0
            or queue.get("counts", {}).get("QUARANTINED", 0) != 0
        )
        return {
            "protocol": "MMT_R31_PRIVATE_ADMIN_OFFLINE_V1",
            "instance_id": state.instance_id,
            "core_id": state.core_id,
            "core_name": state.core_name,
            "panel_revision": state.revision,
            "bindings": tuple({
                "binding_id": b.binding_id,
                "market": b.market,
                "provider": b.provider,
                "symbol": b.symbol,
                "timeframe": b.timeframe,
                "trading_authorized": False,
            } for b in routes),
            "parameters_status": parameters["status"],
            "parameters_sha256": parameters.get("settings_sha256"),
            "analysis_requested": state.analysis_requested,
            "signals_requested": state.telegram_signals_requested,
            "paper_requested": state.paper_orders_requested,
            "risk_allocation": self.center.preview_capital(actor_id, instance_id),
            "local_admin_audit_count": len(
                self.center.audit(actor_id, instance_id)
            ),
            "runtime_health": queue,
            "manual_reconciliation_required_or_unavailable": unresolved,
            "trade_reporting": "REALIZED_PNL_NOT_INDEPENDENTLY_ATTESTED",
            "venue_eligibility_verified": False,
            "telegram_signal_publication_enabled": False,
            "broker_order_send_enabled": False,
            "live_trading_enabled": False,
        }

    def disable_requests(
        self, actor_id: int, instance_id: str, *,
        expected_revision: int, operator_ack: bool = False,
    ) -> dict:
        """Atomically DISABLE all three research requests with Stage12 CAS/audit.

        Never alters an existing order, releases risk, publishes an outbox item,
        or silently unhalts any engine. Old callback/revision cannot override.
        """
        self._actor(actor_id)
        if (operator_ack is not True or type(expected_revision) is not int
                or expected_revision <= 0):
            raise R31AdminRefused("R31_EXPLICIT_DISABLE_AND_REVISION_REQUIRED")
        self.center._mutate(
            actor_id, instance_id, expected_revision,
            "R31_DISABLE_ALL_REQUESTS",
            {"analysis": False, "signals": False, "paper": False},
            lambda row, listing: self.center._db.execute(
                "UPDATE t12_instances SET analysis=0,signals=0,paper=0 "
                "WHERE instance_id=?", (instance_id,),
            ),
        )
        state = self.center.inspect(actor_id, instance_id)
        if (state.analysis_requested or state.telegram_signals_requested
                or state.paper_orders_requested):
            raise R31AdminRefused("R31_DISABLE_VERIFICATION_FAILED")
        return {
            "protocol": "MMT_R31_PRIVATE_ADMIN_OFFLINE_V1",
            "instance_id": instance_id,
            "revision": state.revision,
            "analysis_requested": False,
            "signals_requested": False,
            "paper_requested": False,
            "existing_orders_canceled": False,
            "telegram_signal_publication_enabled": False,
            "live_trading_enabled": False,
        }

    def private_signal_preview(
        self, actor_id: int, instance_id: str, *,
        signal_key: str,
    ) -> dict:
        """Read-only private preview; never claims delivery or issues an ACK."""
        self._actor(actor_id)
        state = self.center.inspect(actor_id, instance_id)
        if self.signals is None or self.signals.enabled is not True:
            raise R31AdminRefused("R31_OFFLINE_SIGNAL_LEDGER_NOT_MOUNTED")
        snapshot = self.signals.snapshot(signal_key)
        binding_ids = {
            item.binding_id for item in self.center.bindings(actor_id, instance_id)
        }
        if (snapshot.instance_id != state.instance_id
                or snapshot.core_id != state.core_id
                or snapshot.binding_id not in binding_ids):
            raise R31AdminRefused("R31_CROSS_INSTANCE_SIGNAL_REFUSED")
        commands = self.signals.commands(signal_key)
        counts = Counter(command.state.value for command in commands)
        unknown = any(v in ("UNKNOWN", "CLAIMED") for v in counts)
        return {
            "protocol": "MMT_R31_PRIVATE_SIGNAL_PREVIEW_V1",
            "instance_id": state.instance_id,
            "signal_key": snapshot.key,
            "binding_id": snapshot.binding_id,
            "signal_state": snapshot.state.value,
            "signal_revision": snapshot.revision,
            "command_count": len(commands),
            "outbox_state_counts": dict(sorted(counts.items())),
            "unresolved_outbox_effects": unknown,
            "locally_simulated_ack_count": counts.get("SIMULATED_ACK", 0),
            "real_telegram_delivery_verified": False,
            "private_route_authentication_verified": False,
            "exactly_once_telegram_delivery_proven": False,
            "network_used": False,
            "telegram_sent": False,
            "broker_orders_sent": False,
            "live_trading_enabled": False,
        }


class R31PrivateTelegramAdminPanel:
    """Mounts commands on an already-authenticated, explicitly built PTB app."""

    def __init__(self, console: R31OfflineAdminConsole) -> None:
        if type(console) is not R31OfflineAdminConsole:
            raise R31AdminRefused("R31_CONSOLE_REQUIRED")
        self.console = console

    async def command(self, update, context) -> None:
        from .trading_control_telegram_v1 import TelegramControlPreviewPanel
        message = getattr(update, "effective_message", None)
        if message is None:
            return
        # Never respond or expose admin UI in group/supergroup/channel contexts.
        # Only a trusted PTB private Update may reach the command interpreter.
        try:
            actor = TelegramControlPreviewPanel._actor(update)
        except ControlRefused:
            return
        try:
            text = getattr(message, "text", None)
            if type(text) is not str or len(text.encode("utf-8")) > 256:
                raise R31AdminRefused("R31_COMMAND_BOUNDS")
            parts = text.split()
            command = parts[0].split("@", 1)[0] if parts else ""
            if command == "/mmt31" and len(parts) == 1:
                view = self.console.overview(actor)
                reply = ("R31 — فقط مدیریت خصوصی و آفلاین\n"
                         "نمونه‌های شما: " + ", ".join(
                             view["accessible_instances"][:25]
                         ) + "\n"
                         "نمایش: /mmt31_view INSTANCE\n"
                         "خاموش‌سازی: /mmt31_off INSTANCE REVISION\n"
                         "رسید محلی: /mmt31_signal INSTANCE SIGNAL_KEY\n"
                         "ارسال سیگنال واقعی و معاملات: غیرفعال")
            elif command == "/mmt31_view" and len(parts) == 2:
                view = self.console.detail(actor, parts[1])
                lines = [
                    "R31 — " + view["instance_id"],
                    "هسته: " + view["core_name"],
                    "نسخه تنظیمات: " + str(view["panel_revision"]),
                    "تحلیل/سیگنال/PAPER (فقط درخواست): "
                    + "/".join("ON" if view[k] else "OFF" for k in (
                        "analysis_requested", "signals_requested", "paper_requested"
                    )),
                    "سلامت صف: " + (
                        "REVIEW_REQUIRED" if
                        view["manual_reconciliation_required_or_unavailable"]
                        else "LOCAL_ONLY"
                    ),
                    "گزارش عملکرد واقعی: تأییدنشده",
                ]
                lines.extend(
                    b["provider"] + ":" + b["symbol"] + " " + b["timeframe"]
                    for b in view["bindings"][:12]
                )
                reply = "\n".join(lines)
            elif command == "/mmt31_off" and len(parts) == 3:
                try:
                    revision = int(parts[2])
                    if str(revision) != parts[2]:
                        raise ValueError
                except ValueError as exc:
                    raise R31AdminRefused("R31_REVISION_INVALID") from exc
                result = self.console.disable_requests(
                    actor, parts[1], expected_revision=revision,
                    operator_ack=True,
                )
                reply = (
                    "درخواست‌های پژوهشی غیرفعال شدند. نسخه: "
                    + str(result["revision"])
                    + "\nاین کار سفارش‌های قبلی را لغو نمی‌کند."
                )
            elif command == "/mmt31_signal" and len(parts) == 3:
                view = self.console.private_signal_preview(
                    actor, parts[1], signal_key=parts[2],
                )
                reply = (
                    "پیش‌نمایش خصوصی؛ ارسال واقعی انجام نشد\n"
                    + "وضعیت سیگنال: " + view["signal_state"]
                    + "\nدفتر ارسال: " + str(view["outbox_state_counts"])
                    + "\nتحویل واقعی تلگرام: تأییدنشده"
                )
            else:
                raise R31AdminRefused("R31_UNKNOWN_COMMAND")
        except (ControlRefused, R31AdminRefused, ValueError):
            reply = "درخواست R31 نامعتبر یا غیرمجاز است."
        # Reply ONLY to the verified private admin chat. NEVER use bot.send_message
        # to any channel ID, target route or signal publisher.
        await message.reply_text(reply)

    def register(self, application) -> None:
        """Registration only: does not start polling or dispatch publications."""
        from telegram.ext import CommandHandler
        for cmd in ("mmt31", "mmt31_view", "mmt31_off", "mmt31_signal"):
            application.add_handler(CommandHandler(cmd, self.command))


__all__ = [
    "R31AdminRefused", "R31OfflineAdminConsole", "R31PrivateTelegramAdminPanel",
]
