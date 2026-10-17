"""Historical R42V signed-source pin remains reproducible after reviewed Ruff edit."""
from __future__ import annotations

import hashlib
from pathlib import Path

from scripts import mmt_r42v_pinned_runtime_acceptance_v1 as r

ROOT = Path(__file__).resolve().parents[2]
NAME = "scripts/mmt_r42_offline_market_account_evidence_v1.py"


def test_reviewed_source_reconstructs_original_historical_pin() -> None:
    body = (ROOT / NAME).read_bytes()
    current_sha, current_sha256 = r._REVIEWED_R42_SOURCE
    historical_sha, historical_sha256 = r.PINS[NAME]
    observed = hashlib.sha1(
        b"blob " + str(len(body)).encode() + b"\0" + body
    ).hexdigest()
    assert observed == current_sha
    assert hashlib.sha256(body).hexdigest() == current_sha256
    assert r._reviewed_r42_matches_historic(
        body, historical_sha, historical_sha256
    )


def test_tampered_source_cannot_reconstruct_historical_commitment() -> None:
    body = (ROOT / NAME).read_bytes() + b"# corruption\n"
    oldsha, old256 = r.PINS[NAME]
    assert not r._reviewed_r42_matches_historic(body, oldsha, old256)


def test_historical_commitment_remains_exact_original() -> None:
    assert r.PINS[NAME] == (
        "070c56bd8774372c40bb61f8316c92988e8c9b35",
        "d4d1aebca64bf81977f5ee5f60cfc1d3833fa2008551378ec8e86916ffdd953d",
    )
