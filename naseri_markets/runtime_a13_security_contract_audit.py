"""A13 source-only security regression audit, no Worker authorization.

AST checks are deliberately narrow: they detect specified drift and cannot
prove host isolation, genuine custody, trusted time, or absence of all Python
reflection/dynamic execution tricks. All output permissions are DENY.
"""
from __future__ import annotations

import ast
import stat
from dataclasses import dataclass
from pathlib import Path

_MODULES = (
    "naseri_markets/runtime_a4_security_evidence.py",
    "naseri_markets/runtime_a5_nonce_custody.py",
    "naseri_markets/runtime_a6_dispatch_fence.py",
    "naseri_markets/runtime_a7_disposable_host_preflight.py",
    "naseri_markets/runtime_a8_supply_chain.py",
    "naseri_markets/runtime_a9_offline_intent.py",
    "naseri_markets/runtime_a10_evidence_anchor.py",
    "naseri_markets/runtime_a11_offline_witness.py",
    "naseri_markets/runtime_a12_offline_recovery.py",
)
_A1 = "naseri_markets/multilang_runtime_a1.py"
_DOCKERFILE = "deploy/runtime_a2/Dockerfile"
_MISSING_GATES = (
    "INDEPENDENT_OCI_AND_PACKAGE_PROVENANCE",
    "DISPOSABLE_HOST_REAL_GVISOR_ATTESTATION",
    "OUT_OF_BAND_LATEST_CHECKPOINT_CUSTODY",
    "TRUSTED_CLOCK_AND_MONOTONIC_ROTATION_EPOCH",
    "INDEPENDENT_REVIEW_OBJECT_AND_WORKER_IDENTITY",
    "INDEPENDENT_KEY_AND_SIGNER_IDENTITY",
)
_FLAG_SUFFIXES = (
    "_authorized", "_permitted", "_certified", "_proven", "_enabled",
    "_installed", "_activated", "_approved",
)


class A13AuditRefused(ValueError):
    """Detected cross-stage contract regression, fail closed."""


@dataclass(frozen=True, slots=True)
class A13AuditReport:
    audited_files: int
    false_security_flag_defaults: int
    hard_stop_checks: int
    remaining_external_gates: tuple[str, ...] = _MISSING_GATES
    status: str = "A13_CONTRACT_CHECKS_PASS_EXTERNAL_SECURITY_GATES_BLOCKED"
    independent_host_certified: bool = False
    media_custody_proven: bool = False
    verified_worker_image_proven: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False
    production_recovery_authorized: bool = False


def _read(root: Path, rel: str) -> bytes:
    if not isinstance(root, Path) or not root.is_absolute() or root.is_symlink():
        raise A13AuditRefused("A13_EXPLICIT_SOURCE_ROOT_REQUIRED")
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise A13AuditRefused("A13_UNEXPECTED_SOURCE_PATH")
    path = root
    for part in Path(rel).parts:
        path = path / part
        if path.is_symlink():
            raise A13AuditRefused("A13_SOURCE_SYMLINK_REFUSED")
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 256 * 1024):
            raise A13AuditRefused("A13_BOUNDED_SOURCE_REQUIRED")
        return path.read_bytes()
    except OSError as exc:
        raise A13AuditRefused("A13_REQUIRED_SOURCE_MISSING") from exc


def _parse(root: Path, rel: str) -> ast.Module:
    try:
        return ast.parse(_read(root, rel).decode("utf-8"), filename=rel)
    except A13AuditRefused:
        raise
    except (UnicodeError, SyntaxError, ValueError, RecursionError) as exc:
        raise A13AuditRefused("A13_SOURCE_NOT_PARSEABLE") from exc


def _method(tree: ast.Module, name: str, owner: str | None = None) -> ast.FunctionDef:
    body: list[ast.stmt] = tree.body
    if owner is not None:
        classes = [x for x in body if isinstance(x, ast.ClassDef) and x.name == owner]
        if len(classes) != 1:
            raise A13AuditRefused("A13_EXPECTED_CLASS_DRIFT")
        body = classes[0].body
    selected = [
        x for x in body if isinstance(x, ast.FunctionDef) and x.name == name
    ]
    if len(selected) != 1:
        raise A13AuditRefused("A13_EXPECTED_METHOD_DRIFT")
    return selected[0]


def _call_name(call: ast.Call) -> str:
    fn = call.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        if isinstance(fn.value, ast.Name):
            return fn.value.id + "." + fn.attr
        return fn.attr
    return ""


def _calls(fn: ast.FunctionDef, name: str) -> list[ast.Call]:
    return [
        x for x in ast.walk(fn)
        if isinstance(x, ast.Call) and _call_name(x) == name
    ]


def _guard_line(fn: ast.FunctionDef, *, translated_denial: bool = False) -> int:
    statements = [
        x for x in fn.body
        if isinstance(x, ast.Expr) and isinstance(x.value, ast.Call)
        and _call_name(x.value) == "require_worker_launch"
    ]
    if not translated_denial:
        if len(statements) != 1:
            raise A13AuditRefused("A13_LAUNCH_GUARD_NOT_DIRECT_AND_UNCONDITIONAL")
        return statements[0].lineno
    # A1.evaluate maps A6's refusal to a public MultilangRefused. The
    # exception handler MUST re-raise a refusal; it may not swallow denial.
    handlers = []
    for stmt in fn.body:
        if not isinstance(stmt, ast.Try) or stmt.orelse or stmt.finalbody:
            continue
        if (len(stmt.body) != 1
                or not isinstance(stmt.body[0], ast.Expr)
                or not isinstance(stmt.body[0].value, ast.Call)
                or _call_name(stmt.body[0].value) != "require_worker_launch"
                or len(stmt.handlers) != 1):
            continue
        handler = stmt.handlers[0]
        if (not isinstance(handler.type, ast.Name)
                or handler.type.id != "RuntimeA6Denied"
                or len(handler.body) != 1
                or not isinstance(handler.body[0], ast.Raise)
                or not isinstance(handler.body[0].exc, ast.Call)
                or _call_name(handler.body[0].exc) != "MultilangRefused"):
            continue
        handlers.append(stmt.body[0].lineno)
    if statements or len(handlers) != 1:
        raise A13AuditRefused("A13_A6_DENIAL_TRANSLATION_NOT_FAIL_CLOSED")
    return handlers[0]


def _deny_contract(tree: ast.Module) -> None:
    fn = _method(tree, "require_worker_launch")
    if not fn.body or not isinstance(fn.body[-1], ast.Raise):
        raise A13AuditRefused("A13_A6_UNCONDITIONAL_DENY_MISSING")
    exc = fn.body[-1].exc
    if (not isinstance(exc, ast.Call)
            or _call_name(exc) != "RuntimeA6Denied"):
        raise A13AuditRefused("A13_A6_DENY_TYPE_DRIFT")
    if (len(_calls(fn, "review_worker_launch")) != 1
            or any(isinstance(x, (ast.Return, ast.Yield, ast.YieldFrom))
                   for x in ast.walk(fn))):
        raise A13AuditRefused("A13_A6_GRANT_OR_PREFLIGHT_BYPASS")


def _a1_choke_points(tree: ast.Module) -> None:
    runner = _method(tree, "_run_oci")
    before = _guard_line(runner)
    for name in ("build_polyglot_command", "subprocess.Popen", "subprocess.run"):
        uses = _calls(runner, name)
        if not uses or min(x.lineno for x in uses) <= before:
            raise A13AuditRefused("A13_OCI_PROCESS_CALL_BEFORE_A6_DENY")
    evaluator = _method(tree, "evaluate", owner="MultiLanguageOfflineHost")
    before = _guard_line(evaluator, translated_denial=True)
    for name in ("_assert_rootless_socket", "_ensure_rootless_daemon", "_run_oci"):
        uses = _calls(evaluator, name)
        if len(uses) != 1 or uses[0].lineno <= before:
            raise A13AuditRefused("A13_DISPATCH_CALL_BEFORE_A6_DENY")


def _stage_checks(tree: ast.Module, label: str) -> int:
    count = 0
    for cls in (x for x in tree.body if isinstance(x, ast.ClassDef)):
        for field in cls.body:
            if (not isinstance(field, ast.AnnAssign)
                    or not isinstance(field.target, ast.Name)
                    or not field.target.id.endswith(_FLAG_SUFFIXES)):
                continue
            if (not isinstance(field.annotation, ast.Name)
                    or field.annotation.id != "bool"
                    or not isinstance(field.value, ast.Constant)
                    or field.value.value is not False):
                raise A13AuditRefused("A13_SECURITY_DEFAULT_GRANT_DRIFT:" + label)
            count += 1
    if not count:
        raise A13AuditRefused("A13_MISSING_DENIAL_FIELDS:" + label)
    if "runtime_a7_" not in label:
        for x in ast.walk(tree):
            if isinstance(x, ast.Import):
                names = [a.name for a in x.names]
            elif isinstance(x, ast.ImportFrom):
                names = [x.module or ""]
            else:
                continue
            if any(n in {"subprocess", "socket", "requests", "docker"} for n in names):
                raise A13AuditRefused("A13_UNEXPECTED_EXECUTOR_IMPORT:" + label)
    return count


def audit_repository(root: Path) -> A13AuditReport:
    """Inspect files only. Never import Workers, run Docker or execute code."""
    trees = {rel: _parse(root, rel) for rel in (*_MODULES, _A1)}
    recipe = _read(root, _DOCKERFILE)
    if b"FROM " not in recipe:
        raise A13AuditRefused("A13_MISSING_WORKER_RECIPE")
    total = sum(_stage_checks(trees[p], p) for p in _MODULES)
    _deny_contract(trees[_MODULES[2]])
    _a1_choke_points(trees[_A1])
    return A13AuditReport(len(trees) + 1, total, 3)


__all__ = ["A13AuditRefused", "A13AuditReport", "audit_repository"]
