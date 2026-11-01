import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"

N_REPLICATES = 1000
RANDOM_SEED = 42


def run_shop_bootstrap():
    started = time.perf_counter()
    con = duckdb.connect(str(WAREHOUSE))

    # Sums and counts per shop, so a replicate uses the same row-weighted formula as the SQL
    shops = con.execute("""
        select state, premise_code, item_key, sum(ln(price)) as sum_ln_p, count(*) as n_obs
        from stg_basket_price
        group by state, premise_code, item_key
    """).df()

    baskets = con.execute("""
        select basket_id,
               case when category_rule = 'BERAS_10KG' then -1 else item_code end as item_key,
               quantity
        from seed_baskets
    """).df()

    deflators = (
        con.execute("select distinct state, cpi_backcast_ratio from fact_basket_state")
        .df().set_index("state")["cpi_backcast_ratio"].to_dict()
    )

    rng = np.random.default_rng(RANDOM_SEED)
    intervals = []

    for state, group in shops.groupby("state"):
        sum_table = group.pivot(index="premise_code", columns="item_key", values="sum_ln_p").fillna(0.0)
        count_table = group.pivot(index="premise_code", columns="item_key", values="n_obs").fillna(0.0)
        sums = sum_table.to_numpy()
        counts = count_table.to_numpy()
        column_of = {item: i for i, item in enumerate(sum_table.columns)}

        base_log_means = sums.sum(axis=0) / counts.sum(axis=0)
        draws = rng.integers(0, len(sums), size=(N_REPLICATES, len(sums)))
        rep_sums = sums[draws].sum(axis=1)
        rep_counts = counts[draws].sum(axis=1)

        # Thin states can draw no shop carrying an item; hold that item at its state mean
        with np.errstate(divide="ignore", invalid="ignore"):
            rep_log_means = rep_sums / rep_counts
        rep_log_means = np.where(rep_counts == 0, base_log_means, rep_log_means)
        rep_prices = np.exp(rep_log_means)

        for basket_id, items in baskets.groupby("basket_id"):
            rep_cost = sum(
                row.quantity * rep_prices[:, column_of[row.item_key]]
                for row in items.itertuples()
            ) * deflators[state]
            low, high = np.quantile(rep_cost, [0.025, 0.975])
            intervals.append({
                "state": state,
                "basket_id": basket_id,
                "ci_lower": round(float(low), 2),
                "ci_upper": round(float(high), 2),
            })

    con.register("tmp_ci", pd.DataFrame(intervals))

    con.execute("""
        update fact_basket_state
        set ci_lower = tmp_ci.ci_lower, ci_upper = tmp_ci.ci_upper
        from tmp_ci
        where fact_basket_state.state = tmp_ci.state
          and fact_basket_state.basket_id = tmp_ci.basket_id
    """)

    con.execute("""
        update mart_burden
        set burden_ci_lower_pct = round(mart_burden.purchases_per_month * f.ci_lower / mart_burden.income_2024 * 100, 2),
            burden_ci_upper_pct = round(mart_burden.purchases_per_month * f.ci_upper / mart_burden.income_2024 * 100, 2)
        from fact_basket_state as f
        where mart_burden.state = f.state
          and mart_burden.basket_id = f.basket_id
    """)

    for table in ["fact_basket_state", "mart_burden"]:
        out_file = PROCESSED_DIR / f"{table}.parquet"
        con.execute(f"copy (select * from {table}) to '{out_file.as_posix()}' (format parquet)")
        con.execute(f"copy {table} to '{out_file.with_suffix('.csv').as_posix()}' (header, delimiter ',')")

    con.close()
    print(f"[OK] Bootstrap completed in {time.perf_counter() - started:4.1f}s ({N_REPLICATES} replicates per state)")


if __name__ == "__main__":
    run_shop_bootstrap()
