"""Explicit NON-PRODUCTION launcher for the new product engine admin panel.

One python-telegram-bot Application; no legacy production modification.
No polling without explicit --nonproduction-poll AND opt-in environment.
No market providers, NYFR code, channel publication or real orders.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .engine_control_store import EngineControlStore, OWNER_CORE_ID
from .integrated_engine_panel import IntegratedEnginePanel


class BotStartupRefused(ValueError):
    """Refuse unsafe implicit Telegram bot startup."""


def build_admin_application(*, token: str, state_dir: str | Path,
                            admin_ids: set[int], owner_ids: set[int],
                            owner_reference: bool = False):
    """Construct one fully mounted PTB app without connecting to Telegram."""
    if (type(token) is not str or not 15 <= len(token) <= 250
            or "\n" in token or "\r" in token
            or not token.split(":", 1)[0].isdigit()
            or not admin_ids or any(type(i) is not int or i <= 0 for i in admin_ids)
            or any(type(i) is not int or i not in admin_ids for i in owner_ids)
            or (owner_reference and not owner_ids)):
        raise BotStartupRefused("BOT_ADMIN_NONPRODUCTION_INPUTS_REQUIRED")
    from telegram.ext import Application
    # Fail before a network call; explicit token is only used by PTB.
    panel = IntegratedEnginePanel(
        state_dir=state_dir, admin_ids=admin_ids, owner_ids=owner_ids)
    with EngineControlStore(state_dir, owner_visible=True) as store:
        if owner_reference:
            store.register_owner_reference(
                engine_id=OWNER_CORE_ID, actor_id=min(owner_ids))
    application = Application.builder().token(token).build()
    panel.register(application)
    return application


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--nonproduction-poll", action="store_true")
    parser.add_argument("--admin-ids", default="")
    parser.add_argument("--owner-ids", default="")
    parser.add_argument("--owner-reference", action="store_true",
                        help="Private metadata-only owner Custom reference")
    args = parser.parse_args(argv)
    try:
        def ids(raw):
            return {int(v) for v in raw.split(",") if v}
        admins = ids(args.admin_ids)
        owners = ids(args.owner_ids)
        if (not admins or any(x <= 0 for x in admins)
                or not owners.issubset(admins)
                or (args.owner_reference and not owners)):
            raise BotStartupRefused("BOT_EXPLICIT_ADMINS_REQUIRED")
        if args.check:
            with EngineControlStore(args.state_dir, owner_visible=False) as store:
                catalog = store.list()
            print(json.dumps({
                "status": "NONPRODUCTION_CONFIG_ONLY",
                "brooks_reference_listed": any(
                    x.engine_id == "brooks_price_action" for x in catalog),
                "visible_public_engines": len(catalog),
                "custom_private_code_loaded": False,
                "telegram_connected": False,
                "live_signals_enabled": False,
                "automatic_channel_delivery": False,
            }, sort_keys=True))
            return 0
        if (os.environ.get("MMT_NONPRODUCTION") != "1"
                or os.environ.get("MMT_PRODUCTION") == "1"
                or not os.environ.get("MMT_DEV_BOT_TOKEN")):
            raise BotStartupRefused("BOT_NONPRODUCTION_ENV_FENCE")
        token = os.environ["MMT_DEV_BOT_TOKEN"]
        application = build_admin_application(
            token=token, state_dir=args.state_dir,
            admin_ids=admins, owner_ids=owners,
            owner_reference=args.owner_reference)
        # Explicitly operator-started standalone DEVELOPMENT bot token only.
        # DO NOT invoke on an existing production token or production server.
        application.run_polling(allowed_updates=["message", "callback_query"])
        return 0
    except (BotStartupRefused, ValueError, OSError) as exc:
        print(f"MMT_ADMIN_REFUSED:{type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
