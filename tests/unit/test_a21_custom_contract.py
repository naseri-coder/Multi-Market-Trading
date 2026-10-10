"""A21 Custom engines: public metadata acceptance with private NYFR never public."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from naseri_markets.a14_packages import PackageRefused, inspect_bundle
from naseri_markets.a21_custom_contract import (
    CustomContractCatalog, CustomContractRefused, PublicCustomListing,
    inspect_custom_paper_fixture, parse_custom_contract,
)
from naseri_markets.contracts import Market
from naseri_markets.plugin_descriptor import parse_descriptor
from test_a7_replay_pipeline import packet, quote

ROOT = Path(__file__).resolve().parents[2]


def contract(*, policy="public_custom", family="generic_custom", **overrides):
    model = {
        "schema_version": 1,
        "engine_id": "custom_demo",
        "engine_version": "1.2.3",
        "publisher": "community.example",
        "markets": ["index", "crypto"],
        "access_policy": policy,
        "strategy_family": family,
        "adapter": "external_contract",
        "abi_version": 1,
        "distribution": "metadata_only",
        "artifact_policy": "no_executable_or_ciphertext",
        "permissions": ["paper_analysis"],
        "runtime_mode": "replay_or_synthetic",
        "execution_authorized": False,
    }
    model.update(overrides)
    return json.dumps(model, sort_keys=True, separators=(",", ":")).encode()


def pin(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    return parse_custom_contract(raw, approved_sha256=pin(raw))


def test_third_party_custom_contract_accepts_multiple_markets_without_install():
    item = parse(contract())
    assert item.engine_id == "custom_demo"
    assert item.engine_version == "1.2.3"
    assert item.publisher == "community.example"
    assert item.markets == frozenset({Market.INDEX, Market.CRYPTO})
    assert item.publicly_discoverable
    assert item.status == "CONTRACT_ONLY_NOT_INSTALLED"
    assert not item.executable_installed
    assert not item.private_source_received
    assert not item.execution_authorized
    assert not item.live_trading_authorized
    assert not item.commercial_license_issued


def test_public_listings_are_derived_from_strict_metadata_and_exclude_private():
    catalog = CustomContractCatalog()
    generic = contract()
    assert catalog.register(generic, approved_sha256=pin(generic)).publicly_discoverable
    owner = contract(policy="owner_only", engine_id="owner_study")
    commercial = contract(policy="commercial_candidate", engine_id="closed_candidate")
    catalog.register(owner, approved_sha256=pin(owner))
    catalog.register(commercial, approved_sha256=pin(commercial))
    result = catalog.public_listings()
    assert result == (
        PublicCustomListing("custom_demo", "1.2.3", ("crypto", "index")),
    )
    assert catalog.public_lookup("owner_study") is None
    assert catalog.public_lookup("closed_candidate") is None
    assert catalog.public_lookup("custom_demo") == result[0]
    assert len(catalog.owner_inventory()) == 3
    assert "owner_study" not in repr(result)
    assert "closed_candidate" not in repr(result)


def test_protected_ny_first_reversal_is_owner_only_never_catalog_public():
    raw = contract(policy="owner_only", family="ny_first_reversal",
                   engine_id="ny_first_reversal", publisher="owner.private")
    item = parse(raw)
    assert item.protected_owner_core
    assert not item.publicly_discoverable
    assert item.status == "CONTRACT_ONLY_NOT_INSTALLED"
    catalog = CustomContractCatalog()
    catalog.register(raw, approved_sha256=pin(raw))
    assert catalog.public_listings() == ()
    assert catalog.public_lookup("ny_first_reversal") is None
    assert item.commercial_license_issued is False


@pytest.mark.parametrize("name", [
    "ny_first_reversal", "nyfirstreversal", "ny_fr", "private_nyfr_core",
    "r0_engine", "NYFR", "alpha_nyfr_market",
])
def test_protected_engine_identifiers_cannot_impersonate_generic_custom(name):
    with pytest.raises(CustomContractRefused, match="PROTECTED_OWNER_EXCLUSIVE"):
        parse(contract(engine_id=name))


@pytest.mark.parametrize("policy", ["public_custom", "commercial_candidate"])
def test_protected_family_never_public_or_commercial_by_label_only(policy):
    with pytest.raises(CustomContractRefused, match="PROTECTED_OWNER_EXCLUSIVE"):
        parse(contract(policy=policy, family="ny_first_reversal",
                       engine_id="owner_nyfr"))


@pytest.mark.parametrize("publisher", ["ny_first_reversal", "NYFR.sales", "r0_engine.licenses"])
def test_protected_publisher_brand_does_not_override_owner_only(publisher):
    with pytest.raises(CustomContractRefused, match="PROTECTED_OWNER_EXCLUSIVE"):
        parse(contract(publisher=publisher))


@pytest.mark.parametrize("payload", [
    {"binary": "c29tZV9vcGFxdWVfY29kZQ=="},
    {"encrypted_zip_b64": "ZW5jcnlwdGVk"},
    {"artifact_url": "https://download.example/plugin.enc"},
    {"entrypoint": "private_nyfr_core:activate"},
    {"command": "python module.py"},
    {"license_key": "fake"},
    {"runtime": "live"},
    {"docker_image": "registry.example/private"},
    {"source_code": "def trade(): pass"},
    {"package_sha256": "a" * 64},
    {"payload_ciphertext": "ciphertext-would-go-here"},
])
def test_cannot_smuggle_executable_encrypted_or_network_artifact_in_contract(payload):
    with pytest.raises(CustomContractRefused, match="EXACT_METADATA_FIELDS_REQUIRED"):
        parse(contract(**payload))


@pytest.mark.parametrize("update", [
    {"execution_authorized": True},
    {"execution_authorized": 0},
    {"artifact_policy": "encrypted_bundle"},
    {"artifact_policy": "code_archive"},
    {"distribution": "public_download"},
    {"distribution": "licensed_download"},
    {"adapter": "python_entrypoint"},
    {"adapter": "local_binary"},
    {"permissions": ["live_trading"]},
    {"permissions": ["paper_analysis", "place_orders"]},
    {"runtime_mode": "production"},
    {"runtime_mode": "live"},
    {"abi_version": True},
    {"abi_version": 2},
    {"schema_version": 2},
    {"schema_version": True},
])
def test_contract_is_fixed_data_only_and_paper_only(update):
    with pytest.raises(CustomContractRefused):
        parse(contract(**update))


@pytest.mark.parametrize("update", [
    {"engine_id": "../secret"},
    {"engine_id": "x"},
    {"engine_version": "1.0-beta"},
    {"publisher": "../trusted"},
    {"markets": []},
    {"markets": ["crypto", "crypto"]},
    {"markets": ["gold"]},
    {"markets": ["index", True]},
    {"strategy_family": "arbitrary_signed_plugin"},
    {"access_policy": "unrestricted"},
])
def test_unknown_unbounded_and_unsafe_metadata_is_rejected(update):
    with pytest.raises(CustomContractRefused):
        parse(contract(**update))


def test_publisher_integrity_pin_is_not_signature_or_commercial_entitlement():
    raw = contract(policy="commercial_candidate", engine_id="private_future")
    with pytest.raises(CustomContractRefused, match="PIN_MISMATCH"):
        parse_custom_contract(raw, approved_sha256="0" * 64)
    with pytest.raises(CustomContractRefused, match="INDEPENDENT_PIN"):
        parse_custom_contract(raw, approved_sha256=pin(raw).upper())
    item = parse(raw)
    assert not item.publicly_discoverable
    assert not item.commercial_license_issued
    assert item.status == "CONTRACT_ONLY_NOT_INSTALLED"


def test_duplicate_registration_is_idempotent_not_replaceable():
    catalog = CustomContractCatalog()
    raw = contract()
    first = catalog.register(raw, approved_sha256=pin(raw))
    assert catalog.register(raw, approved_sha256=pin(raw)) is first
    modified = contract(engine_version="2.0.0")
    with pytest.raises(CustomContractRefused, match="IMMUTABLE_ID_COLLISION"):
        catalog.register(modified, approved_sha256=pin(modified))
    assert catalog.public_lookup("custom_demo").engine_version == "1.2.3"


@pytest.mark.parametrize("raw", [
    b"{}", b"not json", b"\xff", b"[" + b"0" * 4100 + b"]",
    b'{"schema_version":1,"schema_version":1}',
    b'{"value":NaN}',
    b"PK\x03\x04\x00\x00",
    b"\x00" * 512,
])
def test_never_accept_executable_zip_ciphertext_or_malformed_json(raw):
    with pytest.raises(CustomContractRefused):
        parse(raw)


def test_external_paper_envelope_matches_existing_a7_abi_not_broker_order():
    item = parse(contract())
    tick = quote()
    envelope = packet(tick, engine_id="custom_demo", engine_version="1.2.3")
    proposal = inspect_custom_paper_fixture(item, envelope, tick)
    assert proposal.engine_id == "custom_demo"
    assert proposal.engine_version == "1.2.3"
    assert proposal.instrument.market == Market.INDEX
    with pytest.raises(ValueError, match="IDENTITY"):
        inspect_custom_paper_fixture(item, packet(tick), tick)
    with pytest.raises(CustomContractRefused, match="MARKET_OUTSIDE"):
        other = replace(item, markets=frozenset({Market.METAL}))
        inspect_custom_paper_fixture(other, envelope, tick)


def test_old_a8_does_not_mistake_public_custom_metadata_for_runnable_engine():
    # A21 creates NO implicit bridge to A8's existing in-process public
    # adapters. Future A22 must explicitly approve that bridge.
    old = {
        "schema_version": 1, "engine_id": "custom_demo",
        "engine_version": "1.2.3", "publisher": "community.example",
        "visibility": "public", "adapter": "external_contract",
        "abi_version": 1, "markets": ["index"],
        "permissions": ["paper_analysis"],
    }
    raw = json.dumps(old).encode()
    with pytest.raises(ValueError, match="VISIBILITY_ADAPTER_MISMATCH"):
        parse_descriptor(raw, approved_sha256=pin(raw))


def test_a14_synthetic_zip_rejects_ciphertext_delivery_even_with_matching_hash():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("payload.enc", b"ciphertext_example")
    blob = buffer.getvalue()
    with pytest.raises(PackageRefused, match="EXACT_ARCHIVE_MEMBERS_REQUIRED"):
        inspect_bundle(blob, approved_sha256=pin(blob))


def test_public_package_builder_excludes_secret_executables_and_ciphertexts(tmp_path):
    from scripts.a6_prepare_package import prepare
    output = tmp_path / "public-output"
    result = prepare(output)
    assert result["source_was_mutated"] is False
    paths = list(output.rglob("*"))
    assert all(p.is_dir() or p.suffix in {".py", ".toml", ".md"} for p in paths)
    assert not any(p.is_file() and any(word in p.name.casefold()
        for word in ("nyfr", "first_reversal", "r0_engine", "private_core"))
        for p in paths)
    assert (output / "naseri_markets" / "a21_custom_contract.py").exists()
    assert not any(p.suffix in {".zip", ".whl", ".so", ".enc", ".age", ".bin"}
                   for p in paths if p.is_file())


def test_no_owner_private_strategy_source_or_artifact_committed_in_public_tree():
    source = ROOT / "naseri_markets"
    names = {x.name.casefold() for x in source.iterdir() if x.is_file()}
    assert "private_nyfr_core.py" not in names
    assert "r0_engine.py" not in names
    assert not any(x.endswith((".enc", ".age", ".zip", ".whl", ".pyd", ".so", ".bin"))
                   for x in names)


def test_public_custom_listing_objects_do_not_expose_owner_inventory():
    catalog = CustomContractCatalog()
    for raw in (
        contract(policy="public_custom"),
        contract(policy="owner_only", family="ny_first_reversal",
                 engine_id="ny_first_reversal", publisher="owner.private"),
    ):
        catalog.register(raw, approved_sha256=pin(raw))
    listing_json = json.dumps([vars(x) if hasattr(x, "__dict__") else {
        "engine_id": x.engine_id, "engine_version": x.engine_version,
        "markets": x.markets, "status": x.contract_status,
    } for x in catalog.public_listings()])
    assert "ny_first_reversal" not in listing_json
    assert "owner.private" not in listing_json
    assert "CONTRACT_ONLY_NOT_INSTALLED" not in listing_json
