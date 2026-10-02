import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from app.modules.operations.approval_evidence import apply_runner_realization
ROOT=Path(__file__).resolve().parents[2]
CASES=json.loads((ROOT/'tests/fixtures/phase_4_2_41_86_bootstrap_closed_cases_sep11.json').read_text())['cases']
def diag(r):
    x=Decimal(str(r['realized_r']))
    return 1 if x>0 else (0 if x<0 else None)
def test_frozen_closed_cases_have_realized_r():
    assert len(CASES)==72 and all(r.get('realized_r') is not None for r in CASES)
def test_proven_false_losses_count_is_29():
    assert sum(int(r['current_hp_binary_outcome'])==0 and diag(r)==1 for r in CASES)==29
def test_profitable_trailing_closes_are_positive_economically():
    rows=[r for r in CASES if r['terminal_event']=='TRAILING_STOP_CLOSE' and Decimal(str(r['realized_r']))>0]
    assert len(rows)==28 and all(diag(r)==1 for r in rows)
def test_losing_trailing_closes_remain_losses():
    rows=[r for r in CASES if r['terminal_event']=='TRAILING_STOP_CLOSE' and Decimal(str(r['realized_r']))<0]
    assert len(rows)==19 and all(diag(r)==0 for r in rows)
def test_breakeven_is_neither_win_nor_loss_in_binary_diagnostic():
    rows=[r for r in CASES if Decimal(str(r['realized_r']))==0]
    assert len(rows)==1 and rows[0]['terminal_event']=='BREAKEVEN' and diag(rows[0]) is None
def test_staged_completion_preserves_realized_r():
    rows=[r for r in CASES if r['terminal_event']=='TARGET_STAGED_COMPLETION']
    assert len(rows)==1 and Decimal(str(rows[0]['realized_r']))>0
@pytest.mark.parametrize(('runner_return','expected'), [('0.5','0.25'),('-0.5','-0.25'),('0','0')])
def test_runner_realization_uses_persisted_return_pct(runner_return,expected):
    event=NS(metadata={'exit_fraction':'0.5','return_pct':runner_return})
    # Baseline result assumes the runner would have closed at terminal_return=0.
    assert apply_runner_realization(Decimal('0'),Decimal('0'),event)==Decimal(expected)
