"""Chart safety boundary for Phase-4 shadow runtime."""

from __future__ import annotations

from .entities import RuntimeShadowResult


def chart_render_allowed(result: RuntimeShadowResult) -> bool:
    del result
    return False


def assert_no_chart_render(result: RuntimeShadowResult) -> None:
    if chart_render_allowed(result):
        raise RuntimeError("Phase-4 shadow runtime cannot render publication charts")
