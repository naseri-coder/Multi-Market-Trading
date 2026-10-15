"""Pinned, data-only strategy-parameter guard for offline research cores.

No source parsing, imports of strategy code, eval/exec, broker access, state
mutation, implicit defaults or authority to enable signals or trading.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MAX_SCHEMA_BYTES = 48_000
MAX_SETTINGS_BYTES = 8_192
MAX_PARAMETERS = 32
MAX_RELATIONS = 48

_NAME = re.compile(r"[a-z][a-z0-9_]{1,39}\Z", re.ASCII)
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{1,79}\Z", re.ASCII)
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,12})?\Z", re.ASCII)
_CHOICE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,39}\Z", re.ASCII)
_OPERATORS = frozenset({"lt", "lte", "gt", "gte", "eq", "neq"})
_RESERVED = frozenset({
    "api_key", "api_secret", "private_key", "password", "access_token",
    "core_id", "core_version", "account_id", "risk_budget", "leverage",
    "trading_mode", "execution_mode", "live_trading_enabled",
    "broker_orders_enabled", "telegram_publication_enabled",
})


class CoreParametersRefused(ValueError):
    """Fixed refusal codes; no parameter names, values or secrets in errors."""


@dataclass(frozen=True, slots=True)
class ParameterCheck:
    core_id: str
    core_version: str
    schema_sha256: str
    settings_sha256: str
    parameter_count: int
    relation_count: int
    verdict: str = "VALIDATED_OFFLINE_PARAMETER_VALUES_ONLY"
    activation_authorized: bool = False
    broker_orders_enabled: bool = False
    telegram_publication_enabled: bool = False


def _duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise CoreParametersRefused("DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _noninteger(_value: str) -> object:
    raise CoreParametersRefused("NONINTEGER_JSON_NUMBER")


def _nonfinite(_value: str) -> object:
    raise CoreParametersRefused("NONFINITE_JSON_NUMBER")


def _json(raw: object, maximum: int) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= maximum:
        raise CoreParametersRefused("BOUNDED_JSON_BYTES_REQUIRED")
    try:
        parsed = json.loads(
            raw, object_pairs_hook=_duplicate_keys,
            parse_float=_noninteger, parse_constant=_nonfinite,
        )
    except CoreParametersRefused:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise CoreParametersRefused("INVALID_JSON_DOCUMENT") from exc
    if type(parsed) is not dict:
        raise CoreParametersRefused("JSON_OBJECT_REQUIRED")
    return parsed


def _name(value: object) -> str:
    if type(value) is not str or not _NAME.fullmatch(value) or value in _RESERVED:
        raise CoreParametersRefused("UNSAFE_PARAMETER_NAME")
    return value


def _identity(value: object) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise CoreParametersRefused("INVALID_CORE_IDENTITY")
    return value


def _decimal(raw: object) -> Decimal:
    if type(raw) is not str or not _DECIMAL.fullmatch(raw):
        raise CoreParametersRefused("NONCANONICAL_DECIMAL_PARAMETER")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise CoreParametersRefused("NONCANONICAL_DECIMAL_PARAMETER") from exc
    if not result.is_finite() or abs(result) > Decimal("999999999"):
        raise CoreParametersRefused("DECIMAL_PARAMETER_OUT_OF_BOUNDS")
    return result


def _integer(value: object) -> int:
    if type(value) is not int or not -(10**9) <= value <= 10**9:
        raise CoreParametersRefused("INVALID_INTEGER_PARAMETER")
    return value


def _spec(spec: object) -> tuple:
    if type(spec) is not dict:
        raise CoreParametersRefused("INVALID_PARAMETER_SPEC")
    name = _name(spec.get("name"))
    kind = spec.get("kind")
    if kind == "integer":
        if set(spec) != {"name", "kind", "min", "max", "step"}:
            raise CoreParametersRefused("INVALID_INTEGER_SPEC")
        lower, upper, step = (
            _integer(spec[key]) for key in ("min", "max", "step")
        )
        if lower > upper or step <= 0:
            raise CoreParametersRefused("INVALID_INTEGER_RANGE")
        return name, kind, lower, upper, step
    if kind == "decimal":
        if set(spec) != {"name", "kind", "min", "max", "step"}:
            raise CoreParametersRefused("INVALID_DECIMAL_SPEC")
        lower, upper, step = (
            _decimal(spec[key]) for key in ("min", "max", "step")
        )
        if lower > upper or step <= 0:
            raise CoreParametersRefused("INVALID_DECIMAL_RANGE")
        return name, kind, lower, upper, step
    if kind == "boolean":
        if set(spec) != {"name", "kind"}:
            raise CoreParametersRefused("INVALID_BOOLEAN_SPEC")
        return name, kind
    if kind == "choice":
        if set(spec) != {"name", "kind", "options"}:
            raise CoreParametersRefused("INVALID_CHOICE_SPEC")
        options = spec["options"]
        if (type(options) is not list or not 1 <= len(options) <= 16
                or any(type(x) is not str or not _CHOICE.fullmatch(x)
                       for x in options)
                or options != sorted(set(options))):
            raise CoreParametersRefused("INVALID_CHOICE_OPTIONS")
        return name, kind, tuple(options)
    raise CoreParametersRefused("UNSUPPORTED_PARAMETER_TYPE")


def _relation(value: object, specs: dict[str, tuple]) -> tuple[str, str, str]:
    if type(value) is not dict or set(value) != {"left", "op", "right"}:
        raise CoreParametersRefused("INVALID_PARAMETER_RELATION")
    left, operator, right = value["left"], value["op"], value["right"]
    if (type(left) is not str or type(right) is not str
            or type(operator) is not str or operator not in _OPERATORS
            or left == right or left not in specs or right not in specs
            or specs[left][1] not in ("integer", "decimal")
            or specs[right][1] not in ("integer", "decimal")):
        raise CoreParametersRefused("UNSAFE_PARAMETER_RELATION")
    return left, operator, right


def _check_value(spec: tuple, value: object) -> int | Decimal | bool | str:
    kind = spec[1]
    if kind in ("integer", "decimal"):
        parsed = _integer(value) if kind == "integer" else _decimal(value)
        low, high, step = spec[2:]
        if not low <= parsed <= high or (parsed - low) % step != 0:
            raise CoreParametersRefused("PARAMETER_OUTSIDE_REVIEWED_RANGE")
        return parsed
    if kind == "boolean":
        if type(value) is not bool:
            raise CoreParametersRefused("BOOLEAN_VALUE_REQUIRED")
        return value
    if kind == "choice":
        if type(value) is not str or value not in spec[2]:
            raise CoreParametersRefused("UNAPPROVED_CHOICE_VALUE")
        return value
    raise CoreParametersRefused("UNSUPPORTED_PARAMETER_TYPE")


def _check_relation(rule: tuple[str, str, str], values: dict) -> None:
    left, operator, right = rule
    a, b = Decimal(values[left]), Decimal(values[right])
    comparisons = {
        "lt": a < b,
        "lte": a <= b,
        "gt": a > b,
        "gte": a >= b,
        "eq": a == b,
        "neq": a != b,
    }
    if not comparisons[operator]:
        raise CoreParametersRefused("CROSS_PARAMETER_CONSTRAINT_FAILED")


def validate_core_parameters(
    schema_bytes: bytes,
    settings_bytes: bytes,
    *,
    expected_core_id: str,
    expected_core_version: str,
    trusted_schema_sha256: str,
) -> ParameterCheck:
    """Check data against a trusted host-pinned schema, without loading code.

    The *host* must independently obtain/pin the digest from an approved
    core manifest or publisher review. User-supplied self-pins are NOT trust.
    """
    core_id = _identity(expected_core_id)
    core_version = _identity(expected_core_version)
    if type(trusted_schema_sha256) is not str or not _HASH.fullmatch(
        trusted_schema_sha256
    ):
        raise CoreParametersRefused("TRUSTED_SCHEMA_PIN_REQUIRED")
    schema_digest = hashlib.sha256(schema_bytes).hexdigest() if (
        type(schema_bytes) is bytes and len(schema_bytes) <= MAX_SCHEMA_BYTES
    ) else ""
    if not hmac.compare_digest(schema_digest, trusted_schema_sha256):
        raise CoreParametersRefused("SCHEMA_PIN_MISMATCH")
    policy = _json(schema_bytes, MAX_SCHEMA_BYTES)
    supplied = _json(settings_bytes, MAX_SETTINGS_BYTES)
    if set(policy) != {
        "schema_version", "core_id", "core_version", "parameters", "relations"
    } or type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
        raise CoreParametersRefused("INVALID_PARAMETER_POLICY_SCHEMA")
    if set(supplied) != {"schema_version", "core_id", "core_version", "values"}:
        raise CoreParametersRefused("INVALID_PARAMETER_SETTINGS_SCHEMA")
    if (type(supplied["schema_version"]) is not int
            or supplied["schema_version"] != 1):
        raise CoreParametersRefused("INVALID_PARAMETER_SETTINGS_VERSION")
    if (policy["core_id"] != core_id or policy["core_version"] != core_version
            or supplied["core_id"] != core_id
            or supplied["core_version"] != core_version):
        raise CoreParametersRefused("CORE_IDENTITY_OR_VERSION_MISMATCH")
    definition = policy["parameters"]
    if type(definition) is not list or not 1 <= len(definition) <= MAX_PARAMETERS:
        raise CoreParametersRefused("INVALID_PARAMETER_SPEC_COUNT")
    specs: dict[str, tuple] = {}
    for element in definition:
        spec = _spec(element)
        if spec[0] in specs:
            raise CoreParametersRefused("DUPLICATE_PARAMETER_SPEC")
        specs[spec[0]] = spec
    raw_rules = policy["relations"]
    if type(raw_rules) is not list or len(raw_rules) > MAX_RELATIONS:
        raise CoreParametersRefused("INVALID_RELATION_COUNT")
    relations = [_relation(value, specs) for value in raw_rules]
    if len(set(relations)) != len(relations):
        raise CoreParametersRefused("DUPLICATE_PARAMETER_RELATION")
    raw_values = supplied["values"]
    if type(raw_values) is not dict or set(raw_values) != set(specs):
        raise CoreParametersRefused("MISSING_OR_EXTRA_PARAMETER_VALUE")
    parsed = {
        key: _check_value(specs[key], raw_values[key]) for key in specs
    }
    for rule in relations:
        _check_relation(rule, parsed)
    return ParameterCheck(
        core_id, core_version, schema_digest,
        hashlib.sha256(settings_bytes).hexdigest(),
        len(specs), len(relations),
    )


__all__ = [
    "CoreParametersRefused", "ParameterCheck", "validate_core_parameters",
]
