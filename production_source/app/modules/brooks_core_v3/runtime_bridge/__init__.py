"""Brooks Core v3 Phase-4 shadow runtime bridge."""

from .adapter import to_domain_snapshot
from .chart_pipeline import assert_no_chart_render, chart_render_allowed
from .core_orchestrator import BrooksCoreV3ShadowOrchestrator
from .entities import RuntimeShadowResult
from .signal_pipeline import assert_shadow_only, shadow_signal_diagnostics

__all__ = [
    "BrooksCoreV3ShadowOrchestrator",
    "RuntimeShadowResult",
    "to_domain_snapshot",
    "assert_shadow_only",
    "shadow_signal_diagnostics",
    "chart_render_allowed",
    "assert_no_chart_render",
]
