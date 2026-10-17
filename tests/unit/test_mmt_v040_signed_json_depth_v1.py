"""Oversized nesting never escapes the R37/R38 read-only audit boundary.

No signing, installation, network access, keys, or production state are used.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import mmt_r37_offline_signed_manifest_verify_v1 as r37
from scripts import mmt_r38_signed_offline_preview_install_v1 as r38


@pytest.mark.parametrize("nesting", (1100, 1300, 1500))
def test_r37_invalid_deep_manifest_refused_with_stable_error(nesting: int) -> None:
    deep = b"[" * nesting + b"0" + b"]" * nesting
    source = b'{"schema":' + deep + b'}\n'
    assert len(source) < 4096
    with pytest.raises(r37.R37Refused, match="R37_(INVALID_MANIFEST_JSON|MANIFEST_SCHEMA_FIELDS_INVALID)"):
        r37._manifest(source)


@pytest.mark.parametrize("nesting", (1100, 1300, 1500))
def test_r38_deep_policy_refused_without_install_writes(
    tmp_path: Path, nesting: int,
) -> None:
    deep = b"[" * nesting + b"0" + b"]" * nesting
    policy = (
        b'{"active_keys":' + deep
        + b',"min_source_date_epoch":1700000000,'
          b'"revoked_keys":[],"revision":1,"schema":1}\n'
    )
    assert len(policy) < 8192
    path = tmp_path / "deep-policy.json"
    path.write_bytes(policy)
    original = path.read_bytes()
    with pytest.raises(r38.R38Refused, match="R38_(POLICY_JSON_INVALID|POLICY_VALUES_INVALID)"):
        r38._policy(path, hashlib.sha256(original).hexdigest(), "0" * 64)
    assert path.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]


def test_r37_decoder_recursion_normalized_without_propagation(monkeypatch) -> None:
    def nested_failure(*_args, **_kwargs):
        raise RecursionError("artificial JSON decoder depth")

    monkeypatch.setattr(r37.json, "loads", nested_failure)
    with pytest.raises(r37.R37Refused, match="R37_INVALID_MANIFEST_JSON"):
        r37._manifest(b"{}\n")


def test_r38_decoder_recursion_normalized_without_propagation(
    tmp_path: Path, monkeypatch,
) -> None:
    raw = b'{"active_keys":[],"min_source_date_epoch":1700000000,"revoked_keys":[],"revision":1,"schema":1}\n'
    path = tmp_path / "policy.json"
    path.write_bytes(raw)
    def nested_failure(*_args, **_kwargs):
        raise RecursionError("artificial JSON decoder depth")

    monkeypatch.setattr(r38.json, "loads", nested_failure)
    with pytest.raises(r38.R38Refused, match="R38_POLICY_JSON_INVALID"):
        r38._policy(path, hashlib.sha256(raw).hexdigest(), "0" * 64)


def test_r37_encoder_recursion_normalized(monkeypatch) -> None:
    raw = (
        b'{"distribution":"multi-market-trading","purpose":"offline-preview-only",'
        b'"schema":1,"source_commit":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        b'"source_date_epoch":1700000000,"version":"0.4.0rc1",'
        b'"wheel_filename":"multi_market_trading-0.4.0rc1-py3-none-any.whl",'
        b'"wheel_sha256":"'
        + b"0" * 64 + b'","wheel_size":512}\n'
    )
    def nested_failure(*_args, **_kwargs):
        raise RecursionError("artificial JSON encoder depth")

    monkeypatch.setattr(r37.json, "dumps", nested_failure)
    with pytest.raises(r37.R37Refused, match="R37_INVALID_MANIFEST_JSON"):
        r37._manifest(raw)


def test_r38_encoder_recursion_normalized(tmp_path: Path, monkeypatch) -> None:
    raw = b'{"active_keys":[],"min_source_date_epoch":1700000000,"revoked_keys":[],"revision":1,"schema":1}\n'
    path = tmp_path / "policy.json"
    path.write_bytes(raw)
    def nested_failure(*_args, **_kwargs):
        raise RecursionError("artificial JSON encoder depth")

    monkeypatch.setattr(r38.json, "dumps", nested_failure)
    with pytest.raises(r38.R38Refused, match="R38_POLICY_JSON_INVALID"):
        r38._policy(path, hashlib.sha256(raw).hexdigest(), "0" * 64)
