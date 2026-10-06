#!/usr/bin/env python3
"""Run MARC R2 exit-repair development search and untouched holdout."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from research_layer.marc_backtest.data import (
    fetch_binance_vision_monthly_klines,
    resample_15m_to_30m,
    split_contiguous_candles,
)
from research_layer.marc_backtest.engine import BacktestConfig
from research_layer.marc_backtest.entities import BacktestWindowResult
from research_layer.marc_r2_repair.engine import RepairVariant, backtest_repair_variant_window
from research_layer.marc_r2_repair.report import build_repair_report, select_variant
from research_layer.marc_r2_search.report import summarize_windows

DEV=("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT")
HOLD=("ADAUSDT","DOGEUSDT","LINKUSDT","LTCUSDT","BCHUSDT")
VARIANTS=(
    RepairVariant.R1_BASELINE,
    RepairVariant.PARTIAL25_BE_AFTER_1R,
    RepairVariant.FULL_BE_AFTER_1R_TP2_50_RUNNER50,
    RepairVariant.FULL_BE_TP2_50_RUNNER50_COST_BUDGET,
)

def _date(v:str)->datetime:
    return datetime.strptime(v,"%Y-%m-%d").replace(tzinfo=UTC)

def _parser():
    p=argparse.ArgumentParser()
    p.add_argument("--start",type=_date,default=_date("2022-01-01"))
    p.add_argument("--end",type=_date,default=_date("2026-10-01"))
    p.add_argument("--base-cost-bps",type=float,default=6.0)
    p.add_argument("--stress-cost-bps",type=float,default=10.0)
    p.add_argument("--request-delay",type=float,default=0.05)
    p.add_argument("--output-dir",type=Path,default=Path("research_output/marc_r2_exit_repair_v0_1"))
    p.add_argument("--base-url",default="https://data.binance.vision")
    return p

def _segmented(*,candles,symbol,timeframe,start,end,config,variant):
    pieces=[]
    for segment in split_contiguous_candles(candles,timeframe=timeframe):
        if len(segment)<103 or segment[-1].open_time<start or segment[0].open_time>=end:
            continue
        try:
            pieces.append(backtest_repair_variant_window(
                candles=segment,symbol=symbol,timeframe=timeframe,start=start,end=end,
                variant=variant,config=config,
            ))
        except ValueError as exc:
            if str(exc) in {"window has no evaluable candles","not enough candles for MARC backtest"}:
                continue
            raise
    trades=[]; rejections={}; candidates=0; rejected=0
    for x in pieces:
        candidates+=x.candidate_count; rejected+=x.rejected_plan_count; trades.extend(x.trades)
        for reason,count in x.rejection_reasons:
            rejections[reason]=rejections.get(reason,0)+count
    trades.sort(key=lambda t:(t.entry_time,t.source_signal_id))
    return BacktestWindowResult(
        symbol=symbol.upper(),timeframe=timeframe,start=start,end=end,
        candidate_count=candidates,rejected_plan_count=rejected,
        rejection_reasons=tuple(sorted(rejections.items())),trades=tuple(trades),
    )

async def _load(symbol,args):
    a=await fetch_binance_vision_monthly_klines(
        symbol=symbol,start=args.start-timedelta(days=4),end=args.end,timeframe="15m",
        request_delay_seconds=args.request_delay,base_url=args.base_url,
    )
    c15=a.candles; c30=resample_15m_to_30m(c15)
    print(f"MARC_R2_REPAIR_DATA symbol={symbol} c15={len(c15)} c30={len(c30)}",flush=True)
    return c15,c30

async def _run(args):
    config=BacktestConfig(
        base_cost_bps_per_side=args.base_cost_bps,
        stress_cost_bps_per_side=args.stress_cost_bps,
    )
    dev={v.value:[] for v in VARIANTS}
    for symbol in DEV:
        c15,c30=await _load(symbol,args)
        for tf,candles in (("15m",c15),("30m",c30)):
            for v in VARIANTS:
                r=_segmented(candles=candles,symbol=symbol,timeframe=tf,start=args.start,end=args.end,config=config,variant=v)
                dev[v.value].append(r)
                print(f"MARC_R2_REPAIR_DEV variant={v.value} symbol={symbol} tf={tf} trades={len(r.trades)}",flush=True)
    frozen={k:tuple(v) for k,v in dev.items()}
    summaries={k:summarize_windows(v) for k,v in frozen.items()}
    selected=select_variant(summaries)
    print(f"MARC_R2_REPAIR_SELECTED variant={selected}",flush=True)
    hold=None
    if selected is not None:
        items=[]; chosen=RepairVariant(selected)
        for symbol in HOLD:
            c15,c30=await _load(symbol,args)
            for tf,candles in (("15m",c15),("30m",c30)):
                r=_segmented(candles=candles,symbol=symbol,timeframe=tf,start=args.start,end=args.end,config=config,variant=chosen)
                items.append(r)
                print(f"MARC_R2_REPAIR_HOLDOUT variant={selected} symbol={symbol} tf={tf} trades={len(r.trades)}",flush=True)
        hold=tuple(items)
    protocol={
        "development_symbols":list(DEV),
        "untouched_cross_sectional_holdout_symbols":list(HOLD),
        "variants":[v.value for v in VARIANTS],
        "date_range":{"start":args.start.isoformat(),"end_exclusive":args.end.isoformat()},
        "base_cost_bps_per_side":args.base_cost_bps,
        "stress_cost_bps_per_side":args.stress_cost_bps,
        "break_even_timing":"TP1 trigger is known at candle close/intrabar; BE protection becomes active next candle",
        "cost_budget":"stress round-trip entry-notional estimate <= 0.25R",
        "holdout_fetch":"only after one development variant passes frozen selector",
    }
    report=build_repair_report(development=frozen,selected_variant=selected,holdout=hold,protocol=protocol)
    out=args.output_dir.expanduser().resolve(); out.mkdir(parents=True,exist_ok=True)
    path=out/"marc_r2_exit_repair_report.json"
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True),encoding="utf-8")
    for name,s in report["development"]["summaries"].items():
        o=s["overall"]
        print(
            f"MARC_R2_REPAIR_RESULT variant={name} trades={o['trades']} "
            f"base_exp={o['base']['expectancy_r']} base_pf={o['base']['profit_factor']} "
            f"stress_exp={o['stress']['expectancy_r']} stress_pf={o['stress']['profit_factor']}",
            flush=True,
        )
    hs=report["untouched_cross_sectional_holdout"]["summary"]
    if hs is None:
        print("MARC_R2_REPAIR_HOLDOUT_SKIPPED",flush=True)
    else:
        o=hs["overall"]; v=report["untouched_cross_sectional_holdout"]["verdict"]
        print(
            f"MARC_R2_REPAIR_HOLDOUT_RESULT selected={selected} trades={o['trades']} "
            f"base_exp={o['base']['expectancy_r']} base_pf={o['base']['profit_factor']} "
            f"stress_exp={o['stress']['expectancy_r']} stress_pf={o['stress']['profit_factor']} "
            f"classification={v['classification']}",flush=True,
        )
    print(f"MARC_R2_REPAIR_FINAL {report['final_classification']}",flush=True)
    print(f"MARC_R2_REPAIR_REPORT {path}",flush=True)
    return report

def main()->int:
    asyncio.run(_run(_parser().parse_args()))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
