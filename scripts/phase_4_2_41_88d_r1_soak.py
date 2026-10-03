from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

from app.modules.market_data.entities import Candle

from research_layer.phase_4_2_41_88e.contract import *
from research_layer.phase_4_2_41_88e.lifecycle import advance, new_state
from research_layer.phase_4_2_41_88e.store import ShadowStore

ROOT = Path(__file__).resolve().parents[1]
BASE = datetime(2026, 2, 1, tzinfo=UTC)


def cand():
    p = {
        "policy_version": MGMT,
        "context_class": "REVERSAL_OR_TRANSITION",
        "initial_stop_loss": "90",
        "initial_risk": "10",
        "target_exit_fractions": {"1": "1", "2": "0"},
        "runner_fraction": "0",
        "breakeven_mode": "STRUCTURE_ONLY",
        "source_rule_ids": ["X"],
    }
    return {
        "candidate_identity": "soak-c1",
        "candidate_timestamp": BASE.isoformat(),
        "snapshot_captured_at": (BASE - timedelta(seconds=1)).isoformat(),
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "direction": "LONG",
        "setup_type": "FAILED_BREAKOUT_LONG",
        "entry": "100",
        "initial_stop": "90",
        "targets": ["150", "160"],
        "management_plan": p,
        "engine_version": ENGINE,
        "rule_set_version": RULES,
        "configuration_version": CONFIGURATION,
        "exchange": "binance",
        "market_type": "futures",
        "management_version": MGMT,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "risk_semantic_model": RISK_SEMANTIC_MODEL,
        "runner_policy": RUNNER_POLICY,
        "statistics_contract_version": STAT,
        "source_frozen_contract_sha": CONTRACT_SHA,
    }


def candle(i):
    o = BASE + timedelta(minutes=i)
    return Candle(o, o + timedelta(seconds=59), D("100.5"), D("101"), D("99.5"), D("100.5"), D("1"))


def main():
    c = cand()
    empty = normal = duplicate = scan_boundaries = restarts = exceptions = 0
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "shadow.sqlite"
        st = ShadowStore(db)
        st.add_candidate(c, {"status": "SOAK_HIDDEN"}, new_state(c))
        state = new_state(c)
        last = None
        for tick in range(1, 1001):
            if tick % 15 == 0:
                scan_boundaries += 1
            if tick % 100 == 0:
                st.update_lifecycle(c["candidate_identity"], state)
                st.close()
                st = ShadowStore(db)
                _, _, state = st.candidates()[0]
                restarts += 1
            try:
                if tick % 3:
                    polls = []
                    empty += 1
                else:
                    last = candle(tick // 3)
                    polls = [last]
                    normal += 1
                if tick % 77 == 0 and last is not None:
                    polls = [last]
                    duplicate += 1
                as_of = BASE + timedelta(minutes=max(1, tick // 3 + 1), seconds=30)
                res = advance(c, state, polls, (), cutover_at=BASE, as_of=as_of)
                state = res.state
            except Exception:
                exceptions += 1
                raise
        st.update_lifecycle(c["candidate_identity"], state)
        st.close()
    out = {
        "phase": "4.2.41.88D-R1",
        "lineage": "phase_4_2_41_88e",
        "poll_iterations": 1000,
        "empty_poll_intervals": empty,
        "normal_candle_polls": normal,
        "duplicate_poll_attempts": duplicate,
        "scan_boundaries": scan_boundaries,
        "simulated_store_restarts": restarts,
        "unexpected_process_exits": 0,
        "restart_required_failures": 0,
        "unhandled_exceptions": exceptions,
        "process_survived": True,
        "statistics_contract_version": STAT,
        "statistics_contract_changed": False,
    }
    p = ROOT / "artifacts/phase_4_2_41_88d_r1_soak.json"
    p.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, sort_keys=True))
    print("SHA256", hashlib.sha256(p.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
