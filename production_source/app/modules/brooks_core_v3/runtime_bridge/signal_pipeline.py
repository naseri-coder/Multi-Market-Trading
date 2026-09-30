"""Phase-4 shadow signal boundary.

The shadow bridge can be observed and replayed, but it cannot emit a Signal.
"""

from __future__ import annotations

from .entities import RuntimeShadowResult


def assert_shadow_only(result: RuntimeShadowResult) -> None:
    if result.publication_allowed:
        raise RuntimeError("Phase-4 shadow result must never be publishable")
    forbidden = ("decision", "entry_price", "stop_loss", "targets", "leverage")
    for field_name in forbidden:
        if hasattr(result, field_name):
            raise RuntimeError(f"shadow result unexpectedly exposes {field_name}")


def shadow_signal_diagnostics(result: RuntimeShadowResult) -> dict[str, object]:
    assert_shadow_only(result)
    return {
        "source_snapshot_id": result.source_snapshot_id,
        "source_snapshot_hash": result.source_snapshot_hash,
        "publication_allowed": False,
        "blockers": result.blockers,
        "diagnostics": dict(result.diagnostics),
    }
