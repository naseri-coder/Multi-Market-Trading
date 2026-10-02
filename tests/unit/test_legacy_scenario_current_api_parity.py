"""Convergence preserves current APIs and inert research provenance."""

import importlib.util
from pathlib import Path

import pytest
from app.modules.risk_engine.calculator import RiskCalculator
from app.modules.signal_gate.service import SignalGateService
from app.modules.signal_intelligence.probability import ProbabilityAssessment
from setuptools import find_packages

from tests.unit.test_hp_realized_r_policy import quality
from tests.unit.test_risk_semantic_repair import candidate


def test_obsolete_probability_constructor_is_not_restored():
    with pytest.raises(TypeError, match="calibration_status"):
        ProbabilityAssessment(calibration_status="COHORT_MATCHED_MINIMUM_MET")


def test_obsolete_standalone_reward_module_is_absent():
    assert importlib.util.find_spec("app.modules.risk_engine.plan_reward") is None


@pytest.mark.parametrize("phase", ["d", "e", "f"])
def test_research_archive_is_inert_with_provenance(phase):
    root = Path(__file__).resolve().parents[2]
    source = f"research_layer/phase_4_2_41_88{phase}/live_shadow.py"
    archive = root / "docs" / "legacy" / f"{source}.txt"
    text = archive.read_text()
    assert "Historical reference only" in text
    assert f"Original source: {source}" in text
    assert "Original SHA256:" in text
    assert not (root / source).exists()
    assert not any("research_layer" in p for p in find_packages(str(root / "production_source")))
    assert "<historical-project-root>" in text


def test_unknown_execution_policy_remains_fail_closed():
    assert RiskCalculator._structural_points(candidate(method="UNKNOWN_METHOD")) == 0


def test_current_realized_r_gate_still_rejects_major_conflict():
    assessment = quality("CALIBRATED_FAVORABLE")
    assessment.metadata["evidence_conflicts"] = ("MAJOR:synthetic-convergence",)
    decision = SignalGateService().evaluate(assessment)
    assert not decision.approved
    assert "MAJOR_EVIDENCE_CONFLICT" in decision.metadata["failures"]
