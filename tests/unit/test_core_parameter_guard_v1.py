"""Static, offline-only parameter contract tests for reviewed strategy cores."""
from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from copy import deepcopy

import pytest

from naseri_markets.core_parameter_guard_v1 import (
    CoreParametersRefused,
    validate_core_parameters,
)


def schema():
    return {
        "schema_version": 1,
        "core_id": "example_core",
        "core_version": "1.0.0",
        "parameters": [
            {"name": "fast_period", "kind": "integer",
             "min": 2, "max": 100, "step": 1},
            {"name": "slow_period", "kind": "integer",
             "min": 3, "max": 200, "step": 1},
            {"name": "stop_buffer", "kind": "decimal",
             "min": "0.10", "max": "1.00", "step": "0.05"},
            {"name": "max_buffer", "kind": "decimal",
             "min": "0.20", "max": "2.00", "step": "0.05"},
            {"name": "use_confirmation", "kind": "boolean"},
            {"name": "average_type", "kind": "choice", "options": ["ema", "sma"]},
        ],
        "relations": [
            {"left": "fast_period", "op": "lt", "right": "slow_period"},
            {"left": "stop_buffer", "op": "lt", "right": "max_buffer"},
        ],
    }


def settings():
    return {
        "schema_version": 1,
        "core_id": "example_core",
        "core_version": "1.0.0",
        "values": {
            "fast_period": 10, "slow_period": 30,
            "stop_buffer": "0.25", "max_buffer": "0.80",
            "use_confirmation": True, "average_type": "sma",
        },
    }


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def validate(policy=None, values=None, **kw):
    raw_policy = encode(schema() if policy is None else policy)
    raw_values = encode(settings() if values is None else values)
    arguments = {
        "expected_core_id": "example_core",
        "expected_core_version": "1.0.0",
        "trusted_schema_sha256": hashlib.sha256(raw_policy).hexdigest(),
    }
    arguments.update(kw)
    return validate_core_parameters(raw_policy, raw_values, **arguments)


def test_valid_pinned_contract_is_deterministic_and_inert():
    first = validate()
    second = validate()
    assert first == second
    assert first.verdict == "VALIDATED_OFFLINE_PARAMETER_VALUES_ONLY"
    assert first.core_id == "example_core"
    assert first.core_version == "1.0.0"
    assert first.parameter_count == 6
    assert first.relation_count == 2
    assert len(first.schema_sha256) == len(first.settings_sha256) == 64
    assert not first.activation_authorized
    assert not first.broker_orders_enabled
    assert not first.telegram_publication_enabled
    assert not hasattr(first, "values")
    assert not hasattr(first, "execute")
    assert not hasattr(first, "retry")


def test_valid_different_settings_change_digest_not_schema_digest():
    changed = settings()
    changed["values"]["fast_period"] = 11
    before, after = validate(), validate(values=changed)
    assert before.schema_sha256 == after.schema_sha256
    assert before.settings_sha256 != after.settings_sha256


def test_hash_pin_from_trusted_host_blocks_schema_substitution():
    approved = encode(schema())
    malicious = schema()
    malicious["parameters"][0]["max"] = 1000
    unapproved = encode(malicious)
    with pytest.raises(CoreParametersRefused, match="SCHEMA_PIN_MISMATCH"):
        validate_core_parameters(
            unapproved, encode(settings()), expected_core_id="example_core",
            expected_core_version="1.0.0",
            trusted_schema_sha256=hashlib.sha256(approved).hexdigest(),
        )


@pytest.mark.parametrize("claim", [
    "", None, "0" * 64, "z" * 64, "A" * 64, True,
])
def test_invalid_or_mismatched_pin_is_refused(claim):
    with pytest.raises(CoreParametersRefused):
        validate(trusted_schema_sha256=claim)


@pytest.mark.parametrize(("identity", "version"), [
    ("different_core", "1.0.0"), ("example_core", "2.0.0"),
    ("example_core", ""), ("../escape", "1.0.0"),
])
def test_host_core_identity_and_version_cannot_be_confused(identity, version):
    with pytest.raises(CoreParametersRefused):
        validate(expected_core_id=identity, expected_core_version=version)


@pytest.mark.parametrize("wrong", [
    {"core_id": "another_core"}, {"core_version": "2.0.0"},
    {"schema_version": 2}, {"schema_version": True},
])
def test_operator_settings_cannot_claim_another_version_or_core(wrong):
    obj = settings()
    obj.update(wrong)
    with pytest.raises(CoreParametersRefused):
        validate(values=obj)


@pytest.mark.parametrize(("field", "new_value"), [
    ("fast_period", 1), ("fast_period", 101), ("fast_period", True),
    ("fast_period", "10"), ("fast_period", 10.0),
    ("slow_period", 201), ("slow_period", None),
    ("stop_buffer", "0.26"), ("stop_buffer", "0.05"),
    ("stop_buffer", "1.05"), ("stop_buffer", 0.25),
    ("stop_buffer", "NaN"), ("stop_buffer", "Infinity"),
    ("stop_buffer", "1e-1"), ("stop_buffer", "-0.25"),
    ("max_buffer", "0.21"), ("max_buffer", ""),
    ("use_confirmation", 1), ("use_confirmation", "True"),
    ("average_type", "WMA"), ("average_type", True),
])
def test_each_unsafe_parameter_value_fails_closed(field, new_value):
    obj = settings()
    obj["values"][field] = new_value
    with pytest.raises(CoreParametersRefused):
        validate(values=obj)


@pytest.mark.parametrize(("fast", "slow"), [
    (30, 30), (40, 30), (100, 10),
])
def test_fast_period_must_be_strictly_below_slow(fast, slow):
    obj = settings()
    obj["values"]["fast_period"] = fast
    obj["values"]["slow_period"] = slow
    with pytest.raises(CoreParametersRefused, match="CROSS_PARAMETER"):
        validate(values=obj)


def test_decimal_cross_constraint_uses_exact_arithmetic():
    obj = settings()
    obj["values"]["stop_buffer"] = "0.80"
    obj["values"]["max_buffer"] = "0.80"
    with pytest.raises(CoreParametersRefused, match="CROSS_PARAMETER"):
        validate(values=obj)


def test_integer_grid_alignment_is_exact_not_rounded():
    obj = schema()
    obj["parameters"][0] = {
        "name": "fast_period", "kind": "integer",
        "min": 2, "max": 100, "step": 3,
    }
    good = settings()
    good["values"]["fast_period"] = 11
    assert validate(policy=obj, values=good).parameter_count == 6
    bad = settings()
    bad["values"]["fast_period"] = 10
    with pytest.raises(CoreParametersRefused, match="OUTSIDE_REVIEWED_RANGE"):
        validate(policy=obj, values=bad)


def test_decimal_grid_anchor_uses_declared_minimum_exactly():
    obj = schema()
    obj["parameters"][2]["min"] = "0.11"
    obj["parameters"][2]["step"] = "0.07"
    good = settings()
    good["values"]["stop_buffer"] = "0.25"
    assert validate(policy=obj, values=good).relation_count == 2
    bad = settings()
    bad["values"]["stop_buffer"] = "0.24"
    with pytest.raises(CoreParametersRefused, match="OUTSIDE_REVIEWED_RANGE"):
        validate(policy=obj, values=bad)


def test_missing_extra_or_duplicate_parameter_keys_are_refused():
    obj = settings()
    del obj["values"]["fast_period"]
    with pytest.raises(CoreParametersRefused, match="MISSING_OR_EXTRA"):
        validate(values=obj)
    obj = settings()
    obj["values"]["fast_perlod"] = 10
    with pytest.raises(CoreParametersRefused, match="MISSING_OR_EXTRA"):
        validate(values=obj)
    raw_policy = encode(schema())
    raw_value = encode(settings()).replace(
        b'"fast_period":10', b'"fast_period":10,"fast_period":50',
    )
    with pytest.raises(CoreParametersRefused, match="DUPLICATE_JSON"):
        validate_core_parameters(
            raw_policy, raw_value, expected_core_id="example_core",
            expected_core_version="1.0.0",
            trusted_schema_sha256=hashlib.sha256(raw_policy).hexdigest(),
        )


@pytest.mark.parametrize("bad_name", [
    "api_key", "api_secret", "private_key", "password", "access_token",
    "live_trading_enabled", "broker_orders_enabled",
    "telegram_publication_enabled", "execution_mode", "risk_budget",
    "__import__", "__class__", "foo.bar", "AName", "x",
])
def test_privileged_or_invalid_parameter_names_are_denied(bad_name):
    obj = schema()
    obj["parameters"][0]["name"] = bad_name
    with pytest.raises(CoreParametersRefused):
        validate(policy=obj)


@pytest.mark.parametrize("change", [
    {"kind": "formula"},
    {"kind": "python"},
    {"name": "fast_period", "kind": "integer", "min": 1, "max": 20},
    {"name": "fast_period", "kind": "boolean", "default": True},
    {"name": "fast_period", "kind": "integer", "min": 50, "max": 10, "step": 1},
    {"name": "fast_period", "kind": "integer", "min": 1, "max": 10, "step": 0},
    {"name": "fast_period", "kind": "integer", "min": True, "max": 10, "step": 1},
])
def test_invalid_or_executable_parameter_specs_are_refused(change):
    obj = schema()
    obj["parameters"][0].update(change)
    with pytest.raises(CoreParametersRefused):
        validate(policy=obj)


@pytest.mark.parametrize("options", [
    [], ["sma", "sma"], ["sma", "ema"], ["ema", "ema"],
    ["sma", "__import__('os')"], ["sma", ""], ["sma", 42],
])
def test_choice_inventory_requires_unique_sorted_static_tokens(options):
    obj = schema()
    obj["parameters"][-1]["options"] = options
    with pytest.raises(CoreParametersRefused, match="CHOICE_OPTIONS"):
        validate(policy=obj)


@pytest.mark.parametrize("relation", [
    {"left": "fast_period", "op": "eval", "right": "slow_period"},
    {"left": "average_type", "op": "eq", "right": "fast_period"},
    {"left": "fast_period", "op": "lt", "right": "unknown"},
    {"left": "fast_period", "op": "lt", "right": "fast_period"},
    {"left": "fast_period", "op": "lt", "right": "slow_period", "expr": "1"},
])
def test_no_dynamic_code_or_unverified_cross_relations(relation):
    obj = schema()
    obj["relations"][0] = relation
    with pytest.raises(CoreParametersRefused):
        validate(policy=obj)


@pytest.mark.parametrize("op", ["lt", "lte", "gt", "gte", "eq", "neq"])
def test_static_relation_vocabulary_is_executable_code_free(op):
    obj = schema()
    obj["relations"] = [{"left": "fast_period", "op": op, "right": "slow_period"}]
    valid = op in ("lt", "lte", "neq")
    if valid:
        assert validate(policy=obj).relation_count == 1
    else:
        with pytest.raises(CoreParametersRefused, match="CROSS_PARAMETER"):
            validate(policy=obj)


def test_duplicate_cross_constraints_denied():
    obj = schema()
    obj["relations"].append(deepcopy(obj["relations"][0]))
    with pytest.raises(CoreParametersRefused, match="DUPLICATE_PARAMETER_RELATION"):
        validate(policy=obj)


def test_duplicate_and_extra_schema_parameter_rejected():
    obj = schema()
    obj["parameters"].append(deepcopy(obj["parameters"][0]))
    with pytest.raises(CoreParametersRefused, match="DUPLICATE_PARAMETER_SPEC"):
        validate(policy=obj)
    obj = schema()
    obj["unexpected_admin_permission"] = True
    with pytest.raises(CoreParametersRefused, match="POLICY_SCHEMA"):
        validate(policy=obj)


def test_untrusted_private_payload_is_not_reflected_in_exception_or_result():
    token = "MY_PRIVATE_SECRET_TOKEN_DO_NOT_EXPOSE"
    obj = settings()
    obj["values"]["average_type"] = token
    with pytest.raises(CoreParametersRefused) as exc:
        validate(values=obj)
    assert token not in str(exc.value)
    assert token not in repr(exc.value)
    assert token not in repr(validate())


def test_readonly_validation_does_not_mutate_input_or_import_core():
    policy = schema()
    current = settings()
    before_p, before_v = deepcopy(policy), deepcopy(current)
    response = validate(policy, current)
    assert (policy, current) == (before_p, before_v)
    with pytest.raises(FrozenInstanceError):
        response.activation_authorized = True
    assert response.activation_authorized is False


@pytest.mark.parametrize("raw_schema,raw_settings", [
    (b"", encode(settings())),
    (b"{}", b""),
    (b"[]" , encode(settings())),
    (b"\xff", encode(settings())),
    (b'{"broken":NaN}', encode(settings())),
    (encode(schema()), b"x" * 8193),
    (b"x" * 48001, encode(settings())),
])
def test_malformed_and_oversized_documents_refuse_early(raw_schema, raw_settings):
    digest = hashlib.sha256(raw_schema).hexdigest()
    with pytest.raises(CoreParametersRefused):
        validate_core_parameters(
            raw_schema, raw_settings, expected_core_id="example_core",
            expected_core_version="1.0.0", trusted_schema_sha256=digest,
        )


def test_missing_schema_fields_and_extra_values_never_defaulted():
    obj = schema()
    del obj["relations"]
    with pytest.raises(CoreParametersRefused):
        validate(policy=obj)
    obj = settings()
    del obj["values"]
    with pytest.raises(CoreParametersRefused):
        validate(values=obj)
