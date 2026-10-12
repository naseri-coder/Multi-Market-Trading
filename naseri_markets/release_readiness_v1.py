"""Stage 15: read-only public-product release audit, with NO authorization path.

This is a source-tree preflight, not a runtime trust decision. It never imports
external plugin source, runs a market provider, accesses credentials, edits a
repo, deploys, sends Telegram messages or orders. Every release tier is blocked
until an independent product/security/operator release review is completed.
"""
from __future__ import annotations

import hashlib
import json
import stat
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path


class ReadinessRefused(ValueError):
    """Unsafe audit input or unparseable release identity."""


@dataclass(frozen=True, slots=True)
class GateFinding:
    code: str
    status: str
    evidence: str
    priority: str


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    schema_version: int
    source_verdict: str
    release_verdict: str
    preview_distribution: str | None
    preview_version: str | None
    legacy_distribution: str | None
    inspected_sha256: str
    source_gates: tuple[GateFinding, ...]
    release_blockers: tuple[GateFinding, ...]
    offline_preview_candidate: bool
    public_signal_authorized: bool = False
    untrusted_plugins_authorized: bool = False
    live_orders_authorized: bool = False
    telegram_publication_authorized: bool = False
    production_deployment_authorized: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["source_gates"] = list(data["source_gates"])
        data["release_blockers"] = list(data["release_blockers"])
        return data

    def json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


# Minimal source-level boundary: do not silently pass if a critical module is
# absent from the installed public distribution. No evidence of *operation*.
_REQUIRED = {
    "core_api": "naseri_markets/core_api_v1.py",
    "market_data": "naseri_markets/market_data_engine_v1.py",
    "strategy_orchestration": "naseri_markets/strategy_orchestrator_v1.py",
    "research_catalog": "naseri_markets/instrument_registry_v1.py",
    "paper_risk": "naseri_markets/paper_core_risk_bridge_v1.py",
    "paper_positions": "naseri_markets/paper_order_lifecycle_v1.py",
    "signal_outbox": "naseri_markets/offline_signal_lifecycle_v1.py",
    "research": "naseri_markets/strategy_research_lab_v1.py",
    "control_center": "naseri_markets/trading_control_center_v1.py",
    "reliability_gate": "naseri_markets/reliability_acceptance_v1.py",
    "plugin_sdk": "naseri_markets/core_developer_sdk_v1.py",
    "plugin_certification": "naseri_markets/core_certification_v1.py",
    "example_core": "naseri_markets/example_dual_setup_core_v1.py",
    "legacy_runtime": "production_source/app/main.py",
    "installed_preview_entry": "naseri_markets/platform_cli.py",
}

# Release hard blockers are deliberately not derived from self-reported booleans
# or any GitHub test count. Only a separate, authorized operational review can
# change these findings in a future version of the product.
_OPEN_BLOCKERS = (
    ("P0_SINGLE_INTEGRATED_RUNTIME", "No authenticated persistent Stage12-to-Stage7/8/9/10 dispatch and durable handoff exists."),
    ("P0_CLEAN_INSTALLED_OPERATOR_JOURNEY", "A clean installed wheel end-to-end operator journey is not yet proven for the full new product."),
    ("P0_RELEASE_IDENTITY_AND_AUTHORITY", "Root legacy runtime and 0.4.0rc1 preview remain separate; one effective release authority and migration plan are not approved."),
    ("P0_ACCOUNT_RECONCILIATION", "Trusted real account/equity, exposure, remote order state and rollback fencing are not demonstrated."),
    ("P0_PUBLIC_SIGNAL_DELIVERY", "Actual Telegram channel attestation, delivery/edit receipts, UNKNOWN reconciliation and rate limits are unverified."),
    ("P0_AUTHENTIC_MULTI_MARKET_FEEDS", "Authenticated provider provenance, instrument/session quality and regional/account eligibility are unverified."),
    ("P0_EXTERNAL_CORE_CONTAINMENT", "No independent hostile-plugin test of rootless Docker + gVisor on a disposable host."),
    ("P0_SECRETS_OPERATOR_AUTH", "Operator identity, secret custody, revocation and rollout control are not independently audited."),
    ("P0_PRODUCTION_RECOVERY", "Backup/restore, multi-worker crash soak, upgrade/rollback and incident rehearsal are not accepted."),
    ("P1_UNBIASED_PERFORMANCE_EVIDENCE", "No independent genuine-data holdout validates strategy returns; no profitability claim is permitted."),
)


def _regular_read(root: Path, relative: str, *, limit: int = 256_000) -> bytes | None:
    path = root / relative
    if any(part.is_symlink() for part in (path, *path.parents) if part != root.parent):
        raise ReadinessRefused("SYMLINK_IN_REQUIRED_SOURCE")
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(mode) or path.stat().st_size > limit:
        raise ReadinessRefused("NONREGULAR_OR_OVERSIZED_SOURCE")
    return path.read_bytes()


def _metadata(raw: bytes | None, expected_name: str) -> tuple[str | None, str | None, bool]:
    if raw is None:
        return None, None, False
    try:
        obj = tomllib.loads(raw.decode("utf-8"))
        project = obj["project"]
        name, version = project["name"], project["version"]
        if type(name) is not str or type(version) is not str:
            raise ValueError("invalid project metadata")
    except (UnicodeError, KeyError, ValueError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise ReadinessRefused("INVALID_PYPROJECT_METADATA") from exc
    return name, version, name == expected_name


def evaluate_source_readiness(root: str | Path) -> ReadinessReport:
    """Inspect repo *source* only; never approve public or LIVE operation."""
    base = Path(root).absolute()
    if base.is_symlink() or not base.is_dir():
        raise ReadinessRefused("EXISTING_NON_SYMLINK_REPOSITORY_REQUIRED")
    findings: list[GateFinding] = []
    sha = hashlib.sha256()

    def checked(code: str, path: str) -> bytes | None:
        raw = _regular_read(base, path)
        status = "SOURCE_PRESENT" if raw is not None else "MISSING"
        findings.append(GateFinding(code, status, path, "P0"))
        sha.update(path.encode() + b"\0")
        sha.update(hashlib.sha256(raw).digest() if raw is not None else b"MISSING")
        return raw

    legacy_raw = checked("ROOT_LEGACY_DISTRIBUTION", "pyproject.toml")
    preview_raw = checked("ISOLATED_PUBLIC_PREVIEW", "platform_release/pyproject.toml")
    legacy_name, _, legacy_good = _metadata(legacy_raw, "crypto-price-action")
    preview_name, preview_version, preview_good = _metadata(preview_raw, "multi-market-trading")
    preview_ok = bool(preview_good and preview_version == "0.4.0rc1")
    findings.append(GateFinding(
        "SEPARATE_LEGACY_AND_PREVIEW_IDENTITIES",
        "SOURCE_PASS" if legacy_good and preview_ok else "BLOCKED",
        "root crypto-price-action vs. isolated multi-market-trading 0.4.0rc1",
        "P0",
    ))
    for code, path in sorted(_REQUIRED.items()):
        checked("MODULE_" + code.upper(), path)
    pyproject = preview_raw.decode("utf-8") if preview_raw else ""
    # Inspect explicitly supported wheel entry points. Do not claim a different
    # launcher, e.g. old 'markets.sh', installs the new-product release.
    entry_ok = bool(preview_ok and "naseri-markets" in pyproject and
                    "naseri_markets.platform_cli:main" in pyproject)
    findings.append(GateFinding(
        "PREVIEW_CLI_ENTRYPOINT", "SOURCE_PASS" if entry_ok else "BLOCKED",
        "platform_release/pyproject.toml",
        "P0",
    ))
    source_ok = all(f.status in ("SOURCE_PRESENT", "SOURCE_PASS") for f in findings)
    blockers = tuple(GateFinding(code, "UNVERIFIED_BLOCKER", text, code.split("_")[0])
                     for code, text in _OPEN_BLOCKERS)
    return ReadinessReport(
        1,
        "SOURCE_PREFLIGHT_PASS" if source_ok else "SOURCE_PREFLIGHT_BLOCKED",
        "PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE",
        preview_name, preview_version, legacy_name, sha.hexdigest(),
        tuple(findings), blockers, source_ok,
    )


__all__ = ["GateFinding", "ReadinessRefused", "ReadinessReport", "evaluate_source_readiness"]
