# Methodology

The question: **which Malaysian households are under the most pressure, and what drives it?**

Findings live in the README and the report. This file explains how they are made, and it
states no results, so the numbers cannot drift out of step with the data.

## Sources

| Source | Used for | Coverage |
|---|---|---|
| [KPDN PriceCatcher](https://data.gov.my/data-catalogue/pricecatcher), via [`pricecatcher-retail-pricing`](https://github.com/Downey112/pricecatcher-retail-pricing) | Shelf prices of basket items | Shop-level monthly medians, Oct 2025 to Sep 2026 |
| DOSM HIES (`hies_state`, `hies_district`, percentiles) | Income, spending, Gini, poverty | State and district, percentiles 1 to 99 |
| DOSM CPI (`cpi_2d_state`) | Moving prices between dates | Monthly by state, from Jan 2022 |
| DOSM formal wages (`formal_wages_state`) | Wages since the survey | Monthly by state, Jan 2022 to Jun 2026 |
| DOSM `poverty_2024.xlsx`, Table 1.1 | Poverty Line Income (PGK/PLI) | State, 2022 and 2024 |
| DOSM `household_expenditure_2024.xlsx`, Table 4.2 | Spending by group | 13 groups by state, 2024 |
| Belanjawanku 2024/2025 (EPF and SWRC, Universiti Malaya), Table 12 | Reference budgets by household type | 12 cities, 9 household types |

## Baskets

Baskets are defined once, in `data/seed/baskets.csv`. The SQL and the bootstrap both read that
file, so changing a basket means changing one line.

- **Core 7:** rice, chicken, eggs, ikan kembung, cooking oil, sugar, onions.
- **Staples 16:** the sixteen items from the PriceCatcher Retail Pricing project. It has no rice.
- **Staples + rice:** those sixteen plus 10 kg of rice.

Each item is priced at its geometric mean across shops and months within a state.

**Rice is affected by composition.** Monitored brands differ by region. Peninsular states carry
SST 5% items near RM26 and imported items near RM33 to RM36. Sabah and Sarawak carry local brands
such as Sazarice, Vagas Tokou and Uncle Tan. Rice is therefore the state geometric mean across
all monitored 10 kg `BERAS` items, excluding 1 kg pulut. A difference in rice cost between states
is partly a difference in what is on the shelf. `rice_items_count` and `rice_shops_count` are
published beside each cost.

## Aligning dates

Incomes are for 2024 and prices are for Oct 2025 to Sep 2026. Income is not projected forward.
Instead, each state's basket is moved back to 2024 using that state's food CPI (division 01):

    basket_cost_2024 = basket_cost_raw × mean CPI in 2024 / mean CPI, Oct 2025 to Sep 2026

Both costs are kept. The method assumes the basket's prices moved with the state's food index. State food
indexes moved very differently over this period, so `04_validate.py` confirms the top four by
burden are the same without the backcast.

## Burden

    burden % = purchases per month × basket_cost_2024 / income at percentile × 100

Households' real quantities are not observed. The default of **4 purchases a month is an
assumption**, not a measurement, so burden shows relative pressure and is not a share of a real
food bill. `mart_sensitivity` gives 2, 4 and 6, and the report has a slider. The purchase count
scales every state equally, so it cannot change a ranking. The ranking test that matters is
between baskets: `mart_rank_stability` holds the Spearman correlation for each basket pair.

Percentile cut-offs are within each state. P40 here is the 40th percentile of that state's
households, which is not the national B40 definition.

## What drives the gap

Burden is price divided by income, so in logs:

    Var(ln burden) = [Var(ln p) − Cov(ln p, ln y)] + [Var(ln y) − Cov(ln p, ln y)]

The first bracket is the share due to price and the second the share due to income. They sum to
100%. A share can fall below zero when one factor offsets the other. All 16 states count equally,
whatever their population.

`mart_counterfactual` asks the same question state by state. It swaps in a typical price (the
unweighted geometric mean across states, not a population-weighted national price) or Malaysia's
income at the same percentile.

## Budgets and the poverty line

`mart_budget_gap` places each Belanjawanku budget on its state's 2024 income distribution by
counting the percentile cut-offs below it. Read it carefully:

- It is the share of **all** households in the state earning under that budget, **not** the share
  of households of that type.
- A city budget is applied to a whole state, including rural areas, where costs may be lower.
- HIES income is gross, while budgets are spending needs, so the gap is, if anything, understated.
- The budget edition is 2024/2025 and the income year is 2024.
- Perlis and W.P. Labuan have no Belanjawanku city, so they are left out.

`mart_pli` compares P10 with the official poverty line. **The published state PLI is an average.**
PGK is set for each household, by its size and make-up, so a household's own line can sit above or
below that average. Income near the average PLI does not by itself mean a household is poor, and
official poverty rates remain the measure of poverty here.

## Pressure signals

`mart_pressure` ranks each state from 1 (most pressure) on five measures: P10 burden (Staples +
rice), spending as a share of income, share of households under the Married (2 Children) budget,
poverty rate, and real median income growth from 2022 to 2024 (lowest growth = 1).

`pressure_signals` counts the measures on which a state is in the top four. No weights are used.
Perlis and W.P. Labuan are scored out of 4, because they have no budget measure. The count is a
reading aid, not an index. Its measures overlap, since most depend on income.

## Traps avoided

- **Mean against median.** Some districts have mean spending above median income. That compares
  two different households, and it does not show households overspending. Spending ratios are
  always mean over mean, labelled "average household, spending as a share of income".
- **District prices.** Shops are too sparse within districts, so prices stop at state level.
  Districts show income, spending, Gini and poverty only.
- **Districts over time.** District names differ between the 2022 and 2024 releases, so district
  figures are 2024 only, and no change over time is shown.
- **Districts covered.** DOSM's 2024 district file has no rows for Perlis, W.P. Kuala Lumpur,
  W.P. Labuan or W.P. Putrajaya. They appear at state level only, so the district view covers 12
  states.
- **Wages against households.** Formal wages cover formal-sector employees only, not all
  households. Twelve-month windows are used because the monthly median is noisy and rounded.

## Uncertainty

Basket costs carry a 95% interval from a shop-cluster bootstrap: 1,000 resamples of shops, with
replacement, within each state, using a fixed seed. Each resample uses the same row-weighted
formula as the point estimate. The interval covers which shops were sampled, and nothing else: it
does not cover the backcast, the purchase assumption or rice composition.

W.P. Labuan and W.P. Putrajaya have fewer than 30 shops and carry `thin_coverage_flag`.

## Limits

- PriceCatcher is a monitored sample of shop prices. It does not record what households paid.
- HIES percentiles are household income with no adjustment for household size.
- Rent, utilities and transport are outside the baskets. Table 4.2 shows their weight on
  average, but not for lower-income households specifically.
- HIES mean spending by group is for the average household, not for P10.
- Sixteen states is a small sample. Equal weighting gives W.P. Labuan the same pull as Selangor.
