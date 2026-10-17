"""Read-only AST release blocker for value-only MMT_PRODUCTION decisions.

A value-only check such as MMT_PRODUCTION == "1" is not an adequate
nonproduction guard. Explicit presence of this variable, even "0", must
cause offline and PAPER operations to refuse admission.
"""
from __future__ import annotations

import ast
from collections.abc import Mapping


class ProductionGuardRefused(ValueError):
    """Fail-closed, without reporting source bytes or environment values."""


def _is_production_get(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        fn = node.func
        return (isinstance(fn, ast.Attribute)
                and fn.attr in {"get", "getenv"}
                and len(node.args) >= 1
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "MMT_PRODUCTION")
    if isinstance(node, ast.Subscript):
        return (isinstance(node.slice, ast.Constant)
                and node.slice.value == "MMT_PRODUCTION")
    return False


def _is_single_value(node: ast.AST) -> bool:
    return (isinstance(node, ast.Constant)
            and node.value in ("0", "1", "false", "False", "true", "True"))


def scan(source: bytes) -> tuple[int, ...]:
    """Report offending source line numbers; syntax errors also fail closed."""
    try:
        root = ast.parse(source)
    except (SyntaxError, ValueError, UnicodeError) as exc:
        raise ProductionGuardRefused("V040_SOURCE_AST_INVALID") from exc
    violations = set()
    for n in ast.walk(root):
        if not isinstance(n, ast.Compare):
            continue
        operands = [n.left, *n.comparators]
        for a, b in zip(operands, operands[1:], strict=False):
            if (_is_production_get(a) and _is_single_value(b)
                    or _is_production_get(b) and _is_single_value(a)):
                violations.add(n.lineno)
    return tuple(sorted(violations))


def require_no_value_only_guards(modules: Mapping[str, bytes]) -> dict:
    """Check the exact public source bytes before any build directory is made."""
    if not isinstance(modules, Mapping) or not modules:
        raise ProductionGuardRefused("V040_PUBLIC_MODULES_REQUIRED")
    unsafe: dict[str, tuple[int, ...]] = {}
    for name, contents in sorted(modules.items()):
        if not name.startswith("naseri_markets/") or not name.endswith(".py"):
            raise ProductionGuardRefused("V040_PUBLIC_MODULE_NAME_INVALID")
        if not isinstance(contents, bytes):
            raise ProductionGuardRefused("V040_PUBLIC_MODULE_BYTES_REQUIRED")
        matches = scan(contents)
        if matches:
            unsafe[name] = matches
    if unsafe:
        # Intentionally no file contents, environment values or customer secrets.
        raise ProductionGuardRefused(
            f"V040_PRODUCTION_VALUE_ONLY_GUARDS_DENIED:{len(unsafe)}")
    return {"verdict": "V040_SOURCE_PRODUCTION_GUARDS_PASS",
            "module_count": len(modules), "value_only_guards": 0,
            "install_authorized": False, "public_release_authorized": False,
            "live_trading_authorized": False}
