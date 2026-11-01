import os
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
PROCESSED_DIR = ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"

PRICECATCHER_DIR = Path(
    os.environ.get(
        "PRICECATCHER_DIR",
        str(ROOT.parent / "pricecatcher-retail-pricing" / "data" / "processed"),
    )
).resolve()

STAR_TABLES = [
    "dim_state",
    "dim_district",
    "dim_year",
    "dim_month",
    "dim_basket",
    "dim_percentile",
    "dim_spending_group",
    "dim_income_position",
    "dim_household_type",
    "fact_state_year",
    "fact_district_year",
    "fact_percentile",
    "fact_cpi_month",
    "fact_wage_month",
    "fact_basket_state",
    "fact_pli",
    "fact_spending_state",
    "ref_malaysia_year",
    "ref_malaysia_percentile",
    "ref_malaysia_spending",
]

MART_TABLES = [
    "mart_burden",
    "mart_decomposition",
    "mart_counterfactual",
    "mart_real_income",
    "mart_sensitivity",
    "mart_rank_stability",
    "mart_real_wages",
    "mart_budget_gap",
    "mart_pli",
    "mart_pressure",
    "quality_audit",
]


def build():
    if not (PRICECATCHER_DIR / "fact_price_monthly.parquet").exists():
        raise FileNotFoundError(
            f"PriceCatcher processed files not found at {PRICECATCHER_DIR}. "
            f"Set the PRICECATCHER_DIR environment variable."
        )

    # SQL files use paths relative to the repo root
    os.chdir(ROOT)
    con = duckdb.connect(str(WAREHOUSE))
    con.execute(f"set variable pricecatcher_dir = '{PRICECATCHER_DIR.as_posix()}'")

    for sql_file in sorted(SQL_DIR.glob("0*.sql")):
        started = time.perf_counter()
        con.execute(sql_file.read_text(encoding="utf-8"))
        print(f"[OK] {sql_file.name:<20} {time.perf_counter() - started:5.1f}s")

    for table in STAR_TABLES + MART_TABLES:
        rows = con.execute(f"select count(*) from {table}").fetchone()[0]
        out_file = PROCESSED_DIR / f"{table}.parquet"
        con.execute(f"copy (select * from {table} order by all) to '{out_file.as_posix()}' (format parquet)")
        con.execute(f"copy (select * from {table} order by all) to '{out_file.with_suffix('.csv').as_posix()}' (header, delimiter ',')")
        print(f"[OK] {table:<26} -> data/processed ({rows:,} rows)")

    con.close()


if __name__ == "__main__":
    build()
