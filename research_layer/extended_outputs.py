"""Extended research-only exports from the completed SQLite research database."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_output"
DB = OUT / "brooks_research.sqlite"


def configure_paths(*, database: Path, output_dir: Path) -> None:
    global DB, OUT
    database = database.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    if database.suffix not in {".sqlite", ".sqlite3", ".db"}:
        raise ValueError("research database must be an explicit SQLite file")
    if (
        output_dir == ROOT
        or ROOT in output_dir.parents
        and output_dir.name in {"production_source", "app"}
    ):
        raise ValueError("refusing to write research output into runtime source")
    OUT = output_dir
    DB = database
    OUT.mkdir(parents=True, exist_ok=True)


def write_csv(name: str, headers: list[str], rows: list[tuple]) -> None:
    with (OUT / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def quantile_summary(values: list[float]) -> dict[str, float | int | None]:
    clean = np.asarray([v for v in values if v is not None and math.isfinite(v)], dtype=float)
    if not clean.size:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "std": None,
            "min": None,
            "p05": None,
            "p25": None,
            "p75": None,
            "p95": None,
            "max": None,
        }
    return {
        "n": int(clean.size),
        "mean": float(np.mean(clean)),
        "median": float(np.median(clean)),
        "std": float(np.std(clean, ddof=1)) if clean.size > 1 else 0.0,
        "min": float(np.min(clean)),
        "p05": float(np.quantile(clean, 0.05)),
        "p25": float(np.quantile(clean, 0.25)),
        "p75": float(np.quantile(clean, 0.75)),
        "p95": float(np.quantile(clean, 0.95)),
        "max": float(np.max(clean)),
    }


def export_signal_metrics(con: sqlite3.Connection) -> int:
    cur = con.execute("SELECT * FROM signal_metrics ORDER BY signal_id")
    headers = [d[0] for d in cur.description]
    rows = cur.fetchall()
    write_csv("signal_metrics.csv", headers, rows)
    return len(rows)


def export_distributions(con: sqlite3.Connection) -> None:
    cur = con.execute(
        "SELECT realized_r,mfe_r,mae_r,holding_seconds,activation_wait_seconds,"
        "execution_record_delay_seconds,slippage_price,risk_pct,leverage,profit_loss FROM signal_metrics"
    )
    cols = [d[0] for d in cur.description]
    data = list(zip(*cur.fetchall())) if cur.rowcount != 0 else []
    rows = []
    if data:
        for name, values in zip(cols, data):
            summary = quantile_summary([float(v) for v in values if v is not None])
            rows.append((name, *summary.values()))
    headers = ["metric", "n", "mean", "median", "std", "min", "p05", "p25", "p75", "p95", "max"]
    write_csv("metric_distribution_summary.csv", headers, rows)


def export_coverage(con: sqlite3.Connection) -> None:
    total = con.execute("SELECT COUNT(*) FROM signal_metrics").fetchone()[0]
    fields = [
        ("all_signal_rows", "1"),
        ("realized_r", "realized_r IS NOT NULL"),
        ("mfe_r", "mfe_r IS NOT NULL"),
        ("mae_r", "mae_r IS NOT NULL"),
        ("holding_time", "holding_seconds IS NOT NULL"),
        ("activation_wait", "activation_wait_seconds IS NOT NULL"),
        ("execution_record_delay", "execution_record_delay_seconds IS NOT NULL"),
        ("entry_slippage", "slippage_price IS NOT NULL"),
        ("bid_ask_spread", "spread_available != 0"),
        ("ai_score", "ai_score IS NOT NULL"),
        ("risk_score", "risk_score IS NOT NULL"),
        ("quality_score", "quality_score IS NOT NULL"),
        ("confidence", "confidence IS NOT NULL"),
    ]
    rows = []
    for name, predicate in fields:
        count = (
            total
            if predicate == "1"
            else con.execute(f"SELECT COUNT(*) FROM signal_metrics WHERE {predicate}").fetchone()[0]
        )
        rows.append(
            (
                name,
                count,
                total,
                count / total if total else None,
                "NOT_AVAILABLE_FROM_KLINES" if name == "bid_ask_spread" else "RECORDED_OR_DERIVED",
            )
        )
    write_csv(
        "data_collection_coverage.csv",
        ["field", "available_n", "total_n", "coverage", "semantics"],
        rows,
    )


def export_outcomes(con: sqlite3.Connection) -> None:
    rows = con.execute(
        "SELECT exit_reason,COUNT(*) n,AVG(realized_r),AVG(mfe_r),AVG(mae_r),AVG(holding_seconds) "
        "FROM signal_metrics GROUP BY exit_reason ORDER BY n DESC"
    ).fetchall()
    write_csv(
        "outcome_distribution.csv",
        [
            "exit_reason",
            "sample_count",
            "avg_realized_r",
            "avg_mfe_r",
            "avg_mae_r",
            "avg_holding_seconds",
        ],
        rows,
    )


def export_pattern_db_manifest() -> None:
    rows = []
    for path in sorted((OUT / "pattern_databases").glob("*.sqlite")):
        con = sqlite3.connect(path)
        meta = dict(con.execute("SELECT key,value FROM metadata"))
        actual = con.execute("SELECT COUNT(*) FROM actual_samples").fetchone()[0]
        obs = con.execute("SELECT COUNT(*) FROM observational_samples").fetchone()[0]
        quick = con.execute("PRAGMA quick_check").fetchone()[0]
        con.close()
        rows.append((path.name, meta.get("concept"), meta.get("status"), actual, obs, quick))
    write_csv(
        "pattern_database_manifest.csv",
        ["database", "concept", "status", "actual_samples", "observational_samples", "quick_check"],
        rows,
    )


def make_distribution_charts(con: sqlite3.Connection) -> None:
    rows = con.execute(
        "SELECT realized_r,mfe_r,mae_r,risk_pct,holding_seconds FROM signal_metrics"
    ).fetchall()
    if not rows:
        return
    columns = list(zip(*rows))
    specs = [
        ("realized_r", columns[0], "Realized R Distribution", "R"),
        ("mfe_r", columns[1], "MFE Distribution", "R"),
        ("mae_r", columns[2], "MAE Distribution", "R"),
        ("risk_pct", columns[3], "Initial Risk Percentage Distribution", "risk fraction"),
        ("holding_seconds", columns[4], "Holding Time Distribution", "seconds"),
    ]
    for name, values, title, xlabel in specs:
        clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
        if not clean:
            continue
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.hist(clean, bins=min(30, max(8, int(np.sqrt(len(clean))))))
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Count")
        fig.tight_layout()
        fig.savefig(OUT / f"{name}_distribution.png", dpi=160)
        plt.close(fig)


def artifact_manifest() -> None:
    rows = []
    for path in sorted(OUT.rglob("*")):
        if not path.is_file() or path.name in {"research_artifact_manifest.json"}:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(
            {
                "path": path.relative_to(OUT).as_posix(),
                "size": path.stat().st_size,
                "sha256": digest,
            }
        )
    (OUT / "research_artifact_manifest.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )


def append_report_section(con: sqlite3.Connection) -> None:
    report = OUT / "FINAL_RESEARCH_REPORT.md"
    text = report.read_text(encoding="utf-8")
    marker = "\n## Extended Data Collection Audit\n"
    if marker in text:
        text = text.split(marker)[0].rstrip() + "\n"
    coverage = dict(con.execute("SELECT 'signals',COUNT(*) FROM signal_metrics"))
    total = coverage["signals"]
    counts = con.execute(
        "SELECT COUNT(*),SUM(realized_r IS NOT NULL),SUM(mfe_r IS NOT NULL),SUM(mae_r IS NOT NULL),"
        "SUM(holding_seconds IS NOT NULL),SUM(slippage_price IS NOT NULL),"
        "SUM(execution_record_delay_seconds IS NOT NULL),SUM(spread_available) FROM signal_metrics"
    ).fetchone()
    avg = con.execute(
        "SELECT AVG(realized_r),AVG(mfe_r),AVG(mae_r),AVG(holding_seconds),AVG(risk_pct),AVG(leverage) "
        "FROM signal_metrics WHERE realized_r IS NOT NULL"
    ).fetchone()
    section = [
        "",
        "## Extended Data Collection Audit",
        "",
        f"- Signal research rows: **{counts[0]}**; reconstructable realized R: **{counts[1]}**.",
        f"- MFE/MAE coverage: **{counts[2]}/{counts[0]}** and **{counts[3]}/{counts[0]}**; holding-time coverage: **{counts[4]}/{counts[0]}**.",
        f"- Recorded/derived entry slippage coverage: **{counts[5]}/{counts[0]}**; execution-record-delay coverage: **{counts[6]}/{counts[0]}**.",
        f"- Historical bid/ask spread coverage: **{counts[7]}/{counts[0]}**; unavailable fields are never imputed.",
        f"- Aggregate reconstructed metrics on closed R sample: expectancy **{avg[0]:.4f} R**, mean MFE **{avg[1]:.4f} R**, mean MAE **{avg[2]:.4f} R**, mean holding time **{avg[3] / 60:.1f} minutes**.",
        f"- Mean initial risk fraction: **{avg[4]:.6f}**; mean leverage: **{avg[5]:.3f}x**.",
        "- Extended exports: `signal_metrics.csv`, `metric_distribution_summary.csv`, `data_collection_coverage.csv`, `outcome_distribution.csv`, and `pattern_database_manifest.csv`.",
        "- Additional distribution charts cover realized R, MFE, MAE, initial risk and holding time.",
    ]
    report.write_text(text.rstrip() + "\n" + "\n".join(section) + "\n", encoding="utf-8")


def main(*, database: Path, output_dir: Path) -> None:
    configure_paths(database=database, output_dir=output_dir)
    con = sqlite3.connect(DB)
    try:
        signal_rows = export_signal_metrics(con)
        export_distributions(con)
        export_coverage(con)
        export_outcomes(con)
        export_pattern_db_manifest()
        make_distribution_charts(con)
        append_report_section(con)
    finally:
        con.close()
    artifact_manifest()
    print("EXTENDED_RESEARCH_EXPORTS=PASS", "signal_rows", signal_rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    main(database=args.database, output_dir=args.output_dir)
