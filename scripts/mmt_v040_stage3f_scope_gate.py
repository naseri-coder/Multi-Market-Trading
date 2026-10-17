"""Read-only Stage 3F release-scope claim gate; NOT a release authorization.

This locks truthful disclosure of the two failed public market-data probes.
A passing check cannot waive a failed smoke, disable packaged entrypoints,
authenticate a publisher or grant human approval.
"""
from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path

_SCOPE = "docs/MMT_V0_4_0_STAGE3F_SCOPE_CONTRACT.json"
_PROBE = "docs/evidence/MMT_V0_4_0_STAGE3E_PROVIDER_RESULTS.json"
_PACKAGE = "platform_release/pyproject.toml"

EXPECTED_SCOPE = {
    "base_distribution": "multi-market-trading",
    "candidate_version": "0.4.0rc1",
    "commercial_live_claim": "NOT_VERIFIED_NOT_IN_RELEASE_SCOPE",
    "deployment_status": "DENIED",
    "eligible_cli": ["naseri-brooks-replay", "naseri-paper-demo"],
    "evidence_record": _PROBE,
    "human_scope_review": "PENDING",
    "live_order_execution": "DENIED",
    "market_data_network_claim": "UNVERIFIED",
    "operator_identity": "PENDING",
    "private_ny_engine": "EXCLUDED",
    "publisher_identity": "PENDING",
    "release_authorized": False,
    "release_lane": "OFFLINE_REPLAY_AND_DISPOSABLE_PAPER_ONLY",
    "schema": 1,
    "stable_target_version": "0.4.0",
    "status": "DRAFT_SCOPE_CONTRACT_NOT_A_WAIVER",
}
EXPECTED_PROBE = {
    "assurance": "EXTERNAL_PROVIDER_LIVE_SMOKE_NOT_VERIFIED",
    "binance_futures_http_status": 451,
    "bybit_spot_http_status": 403,
    "candidate_source_sha": "77a0b19f89485d1e8b7a4cb43caa01eed123af47",
    "consumer_permissions": "PUBLIC_GET_READ_ONLY_NO_CREDENTIALS_NO_ORDERS",
    "evidence_job_id": 117482570405,
    "evidence_run_id": 39062296330,
    "failed_count": 2,
    "passed_count": 0,
    "schema": 1,
}
EXPECTED_CLI = {
    "naseri-brooks-replay": "naseri_markets.brooks_replay:main",
    "naseri-paper-demo": "naseri_markets.paper_demo_cli_v1:main",
}


class ReleaseScopeRefused(ValueError):
    """Refuse ambiguous or promoted release claims without printing file content."""


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseScopeRefused("SCOPE3F_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _read_json(path: Path) -> dict:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
            raise ReleaseScopeRefused("SCOPE3F_UNSAFE_JSON_PATH")
        raw = path.read_bytes()
        if b"\x00" in raw:
            raise ReleaseScopeRefused("SCOPE3F_INVALID_JSON")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
        if type(value) is not dict:
            raise ReleaseScopeRefused("SCOPE3F_INVALID_JSON_SHAPE")
        canonical = (json.dumps(value, sort_keys=True, indent=2,
                                ensure_ascii=True, allow_nan=False) + "\n").encode()
        if raw != canonical:
            raise ReleaseScopeRefused("SCOPE3F_NONCANONICAL_JSON")
        return value
    except ReleaseScopeRefused:
        raise
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        raise ReleaseScopeRefused("SCOPE3F_INVALID_JSON") from exc


def audit(repository: Path) -> dict:
    if not isinstance(repository, Path) or not repository.is_absolute():
        raise ReleaseScopeRefused("SCOPE3F_ABSOLUTE_REPOSITORY_REQUIRED")
    if repository.is_symlink() or not repository.is_dir():
        raise ReleaseScopeRefused("SCOPE3F_UNSAFE_REPOSITORY")
    scope = _read_json(repository / _SCOPE)
    evidence = _read_json(repository / _PROBE)
    if scope != EXPECTED_SCOPE:
        raise ReleaseScopeRefused("SCOPE3F_SCOPE_ESCALATION_OR_DRIFT")
    if evidence != EXPECTED_PROBE:
        raise ReleaseScopeRefused("SCOPE3F_PROVIDER_FAILURE_HISTORY_DRIFT")

    package_file = repository / _PACKAGE
    try:
        if (package_file.is_symlink() or not package_file.is_file()
                or package_file.stat().st_size > 100_000):
            raise ReleaseScopeRefused("SCOPE3F_UNSAFE_PACKAGE_METADATA")
        project = tomllib.loads(package_file.read_text("utf-8"))["project"]
        if (project["name"] != EXPECTED_SCOPE["base_distribution"]
                or project["version"] != EXPECTED_SCOPE["candidate_version"]
                or project["requires-python"] != ">=3.12,<3.13"
                or project["dependencies"] != []
                or not isinstance(project["scripts"], dict)
                or any(project["scripts"].get(key) != value
                       for key, value in EXPECTED_CLI.items())):
            raise ReleaseScopeRefused("SCOPE3F_PACKAGE_METADATA_DRIFT")
    except ReleaseScopeRefused:
        raise
    except (OSError, UnicodeError, KeyError, ValueError, TypeError) as exc:
        raise ReleaseScopeRefused("SCOPE3F_PACKAGE_METADATA_DRIFT") from exc

    # Other CLI entrypoints may still be present in the preview package.
    # This manifest limits review claims; it is NOT an execution sandbox.
    return {
        "verdict": "SCOPE3F_OFFLINE_PAPER_CLAIMS_TRUTHFUL_REVIEW_PENDING",
        "candidate_version": "0.4.0rc1",
        "public_provider_live_smokes_passed": 0,
        "public_provider_live_smokes_failed": 2,
        "network_market_data_verified": False,
        "actual_runtime_live_routes_proven_disabled": False,
        "human_scope_review_complete": False,
        "publisher_signature_approved": False,
        "merge_authorized": False,
        "release_authorized": False,
        "live_trading_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    args = parser.parse_args()
    try:
        verdict = audit(args.repository)
    except ReleaseScopeRefused as exc:
        print(json.dumps({"verdict": str(exc), "release_authorized": False}))
        return 2
    print(json.dumps(verdict, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
