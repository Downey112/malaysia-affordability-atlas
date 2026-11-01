import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"

failures = []


def check(condition, message):
    print(f"[{'PASS' if condition else 'FAIL'}] {message}")
    if not condition:
        failures.append(message)


def read(name):
    return pd.read_parquet(PROCESSED_DIR / f"{name}.parquet")


def validate():
    dim_state = read("dim_state")
    dim_district = read("dim_district")
    states = set(dim_state["state"])

    check(dim_state["state"].is_unique and len(dim_state) == 16, "dim_state: 16 unique states")
    check(dim_district["district_key"].is_unique and len(dim_district) == 162, "dim_district: 162 unique keys")
    check(len(read("dim_basket")) == 3, "dim_basket: 3 baskets")
    check(len(read("dim_percentile")) == 99, "dim_percentile: 99 percentiles")
    check(len(read("dim_spending_group")) == 13, "dim_spending_group: 13 groups")

    fact_state = read("fact_state_year")
    fact_district = read("fact_district_year")
    fact_pct = read("fact_percentile")
    fact_cpi = read("fact_cpi_month")
    fact_wage = read("fact_wage_month")
    fact_basket = read("fact_basket_state")
    fact_pli = read("fact_pli")
    fact_spending = read("fact_spending_state")

    # No orphans: every fact joins to its dimensions
    for name, table in [
        ("fact_state_year", fact_state), ("fact_percentile", fact_pct), ("fact_cpi_month", fact_cpi),
        ("fact_wage_month", fact_wage), ("fact_basket_state", fact_basket),
        ("fact_pli", fact_pli), ("fact_spending_state", fact_spending),
    ]:
        check(set(table["state"]) == states, f"{name}: states match dim_state exactly")
    check(set(fact_district["district_key"]) == set(dim_district["district_key"]), "fact_district_year: keys match dim_district")
    # DOSM's 2024 district file has no rows for these four, which are state-level only
    no_districts = {"Perlis", "W.P. Kuala Lumpur", "W.P. Labuan", "W.P. Putrajaya"}
    check(set(fact_district["state"]) == states - no_districts, "fact_district_year: covers the 12 states with district rows")
    check(set(fact_pct["percentile"]) == set(read("dim_percentile")["percentile"]), "fact_percentile: percentiles match dim_percentile")
    months = set(read("dim_month")["month"])
    check(set(fact_cpi["month"]) <= months and set(fact_wage["month"]) <= months, "monthly facts: months exist in dim_month")
    check(len(fact_spending) == 208, "fact_spending_state: 208 rows (16 states x 13 groups)")
    check(not fact_pct["income"].isna().any(), "fact_percentile: no null incomes")

    # Published benchmarks
    ref = read("ref_malaysia_year").set_index("year")
    check(ref.loc[2024, "income_mean"] == 9155, "ref_malaysia_year: 2024 mean income 9155")
    check(ref.loc[2024, "income_median"] == 7017, "ref_malaysia_year: 2024 median income 7017")
    check(ref.loc[2022, "pli"] == 2589 and ref.loc[2024, "pli"] == 2705, "ref_malaysia_year: PLI 2589 and 2705")

    ref_pct = read("ref_malaysia_percentile")
    p50 = ref_pct[(ref_pct["year"] == 2024) & (ref_pct["percentile"] == 50)]["income"].iloc[0]
    check(p50 == 7017, "ref_malaysia_percentile: 2024 P50 equals published median")

    medians = fact_pct[(fact_pct["year"] == 2024) & (fact_pct["percentile"] == 50)].set_index("state")["income"]
    published = fact_state[fact_state["year"] == 2024].set_index("state")["income_median"]
    check((medians - published).abs().max() == 0, "fact_percentile: every state's 2024 P50 equals its published median")

    staples = fact_basket[fact_basket["basket_id"] == "staples_16"].set_index("state")["basket_cost_raw"]
    check(abs(staples["Perak"] - 112.77) < 0.01, "fact_basket_state: Staples 16 reproduces sibling Perak RM112.77")
    check(abs(staples["W.P. Putrajaya"] - 128.47) < 0.01, "fact_basket_state: Staples 16 reproduces sibling Putrajaya RM128.47")

    spending_sums = fact_spending.groupby("state")["spend_rm"].sum()
    hies_spending = fact_state[fact_state["year"] == 2024].set_index("state")["expenditure_mean"]
    gap = (spending_sums - hies_spending).abs().max()
    check(gap <= 5.0, f"fact_spending_state: groups sum to HIES expenditure_mean within RM5 (max gap RM{gap:.2f})")

    # Percentiles only ever rise
    rising = all(
        np.all(np.diff(group.sort_values("percentile")["income"].to_numpy()) >= 0)
        for _, group in fact_pct.groupby(["state", "year"])
    )
    check(rising, "fact_percentile: cut-offs never fall as the percentile rises")

    # Baskets
    expected_items = {"core": 7, "staples_16": 16, "staples_plus_rice": 17}
    check(all(fact_basket["items_priced"] == fact_basket["basket_id"].map(expected_items)), "fact_basket_state: every basket fully priced in every state")
    check(fact_basket["ci_lower"].notna().all() and fact_basket["ci_upper"].notna().all(), "fact_basket_state: intervals populated")
    check((fact_basket["ci_lower"] <= fact_basket["basket_cost_2024"]).all(), "fact_basket_state: ci_lower <= point estimate")
    check((fact_basket["basket_cost_2024"] <= fact_basket["ci_upper"]).all(), "fact_basket_state: point estimate <= ci_upper")
    rice = fact_basket[fact_basket["basket_id"] == "core"]
    check(rice["rice_items_count"].between(1, 16).all() and rice["rice_items_count"].nunique() > 1, "fact_basket_state: rice item counts vary by state")
    flagged = set(dim_state.loc[dim_state["thin_coverage_flag"], "state"])
    check(flagged == {"W.P. Labuan", "W.P. Putrajaya"}, "dim_state: thin coverage flags only Labuan and Putrajaya")

    # The backcast must not decide who ranks worst
    burden = read("mart_burden")
    worst = burden[(burden["basket_id"] == "staples_plus_rice") & (burden["percentile"] == 10)]
    raw_cost = fact_basket[fact_basket["basket_id"] == "staples_plus_rice"].set_index("state")["basket_cost_raw"]
    raw_burden = raw_cost / worst.set_index("state")["income_2024"]
    check(set(raw_burden.nlargest(4).index) == set(worst.nsmallest(4, "rank_burden")["state"]), "mart_burden: top four unchanged without the backcast")

    # Marts
    decomposition = read("mart_decomposition")
    check(len(decomposition) == 12, "mart_decomposition: 12 rows")
    check(np.allclose(decomposition["sum_shares_pct"], 100.0, atol=0.02), "mart_decomposition: shares sum to 100")

    stability = read("mart_rank_stability")
    check(len(stability) == 12, "mart_rank_stability: 12 rows (3 basket pairs x 4 percentiles)")

    check(burden["burden_ci_lower_pct"].notna().all(), "mart_burden: intervals populated")

    check(len(read("mart_real_wages")) == 16, "mart_real_wages: 16 states")
    budget_gap = read("mart_budget_gap")
    check(len(budget_gap) == 14 * 9, "mart_budget_gap: 126 rows (14 states x 9 household types)")
    check(set(budget_gap["state"]).isdisjoint({"Perlis", "W.P. Labuan"}), "mart_budget_gap: Perlis and Labuan absent")
    check(budget_gap["pct_households_below"].between(0, 99).all(), "mart_budget_gap: percent within range")

    pressure = read("mart_pressure")
    check(len(pressure) == 16, "mart_pressure: 16 states")
    unmatched = pressure["state"].isin(["Perlis", "W.P. Labuan"])
    check((pressure.loc[unmatched, "signals_available"] == 4).all(), "mart_pressure: Perlis and Labuan out of 4")
    check((pressure["pressure_signals"] <= pressure["signals_available"]).all(), "mart_pressure: signals within available")

    if failures:
        print(f"\nValidation failed: {len(failures)} check(s) did not pass.")
        sys.exit(1)
    print("\nAll validation checks passed.")


if __name__ == "__main__":
    validate()
