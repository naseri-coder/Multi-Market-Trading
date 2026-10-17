"""Isolated scope-claim regression tests, with no external network or credentials."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import mmt_v040_stage3f_scope_gate as gate

REPO = Path(__file__).resolve().parents[2]
SOURCE_PACKAGE = REPO / "platform_release" / "pyproject.toml"


def canonical(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, indent=2,
                       ensure_ascii=True, allow_nan=False) + "\n").encode()


class Stage3FScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mmt-stage3f-unit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scope = self.root / "docs" / "MMT_V0_4_0_STAGE3F_SCOPE_CONTRACT.json"
        self.probe = self.root / "docs" / "evidence" / "MMT_V0_4_0_STAGE3E_PROVIDER_RESULTS.json"
        self.package = self.root / "platform_release" / "pyproject.toml"
        self.scope.parent.mkdir(parents=True)
        self.probe.parent.mkdir(parents=True)
        self.package.parent.mkdir(parents=True)
        self.scope.write_bytes(canonical(gate.EXPECTED_SCOPE))
        self.probe.write_bytes(canonical(gate.EXPECTED_PROBE))
        self.package.write_bytes(SOURCE_PACKAGE.read_bytes())

    def check_denied(self, code):
        with self.assertRaisesRegex(gate.ReleaseScopeRefused, code):
            gate.audit(self.root)

    def test_current_scope_cannot_grant_release(self):
        x = gate.audit(self.root)
        self.assertFalse(x["release_authorized"])
        self.assertFalse(x["network_market_data_verified"])
        self.assertFalse(x["human_scope_review_complete"])
        self.assertFalse(x["actual_runtime_live_routes_proven_disabled"])
        self.assertEqual(x["public_provider_live_smokes_failed"], 2)

    def test_real_repo_evidence_is_canonical_and_accepted_as_unapproved(self):
        v = gate.audit(REPO)
        self.assertEqual(v["verdict"], "SCOPE3F_OFFLINE_PAPER_CLAIMS_TRUTHFUL_REVIEW_PENDING")

    def test_cannot_promote_external_live_market_feed(self):
        obj = dict(gate.EXPECTED_SCOPE, market_data_network_claim="VERIFIED")
        self.scope.write_bytes(canonical(obj))
        self.check_denied("SCOPE_ESCALATION_OR_DRIFT")

    def test_cannot_claim_actual_release_authorized(self):
        self.scope.write_bytes(canonical({**gate.EXPECTED_SCOPE, "release_authorized": True}))
        self.check_denied("SCOPE_ESCALATION_OR_DRIFT")

    def test_cannot_claim_human_approval(self):
        self.scope.write_bytes(canonical({**gate.EXPECTED_SCOPE, "human_scope_review": "APPROVED"}))
        self.check_denied("SCOPE_ESCALATION_OR_DRIFT")

    def test_cannot_claim_real_live_orders(self):
        payload = {**gate.EXPECTED_SCOPE, "live_order_execution": "ALLOWED"}
        self.scope.write_bytes(canonical(payload))
        self.check_denied("SCOPE_ESCALATION_OR_DRIFT")

    def test_cannot_claim_success_for_failed_live_provider(self):
        self.probe.write_bytes(canonical({**gate.EXPECTED_PROBE, "passed_count": 2}))
        self.check_denied("PROVIDER_FAILURE_HISTORY_DRIFT")

    def test_cannot_swap_provider_status_to_success(self):
        self.probe.write_bytes(canonical({
            **gate.EXPECTED_PROBE, "binance_futures_http_status": 200
        }))
        self.check_denied("PROVIDER_FAILURE_HISTORY_DRIFT")

    def test_duplicate_json_keys_refused(self):
        self.scope.write_bytes(b'{"schema":1,"schema":1}\n')
        self.check_denied("DUPLICATE_JSON_KEY")

    def test_production_version_metadata_swap_refused(self):
        raw = self.package.read_text()
        self.assertIn('version = "0.4.0rc1"', raw)
        self.package.write_text(raw.replace('version = "0.4.0rc1"', 'version = "0.4.0"'))
        self.check_denied("PACKAGE_METADATA_DRIFT")

    def test_unapproved_cli_entrypoint_mutation_refused(self):
        raw = self.package.read_text()
        self.package.write_text(raw.replace(
            "naseri_markets.paper_demo_cli_v1:main", "naseri_markets.live_cli:main"
        ))
        self.check_denied("PACKAGE_METADATA_DRIFT")

    def test_scope_symlink_refused(self):
        self.scope.unlink()
        self.scope.symlink_to(self.probe)
        self.check_denied("UNSAFE_JSON_PATH")

    def test_observation_drop_refused(self):
        self.probe.unlink()
        self.check_denied("UNSAFE_JSON_PATH")

    def test_scope_extras_refused(self):
        self.scope.write_bytes(canonical({**gate.EXPECTED_SCOPE, "official": True}))
        self.check_denied("SCOPE_ESCALATION_OR_DRIFT")


if __name__ == "__main__":
    unittest.main()
