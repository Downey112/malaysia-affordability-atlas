-- 04_marts.sql
-- Marts answering: which households are under the most pressure, and what drives it?

-- Q1. What share of income does the basket take, by state and income position?
create or replace table mart_burden as
select
    f.state,
    f.basket_id,
    p.percentile,
    p.income as income_2024,
    f.basket_cost_2024,
    4 as purchases_per_month,
    round(4.0 * f.basket_cost_2024, 2) as monthly_basket_spend,
    round(4.0 * f.basket_cost_2024 / p.income * 100, 2) as burden_pct,
    cast(null as double) as burden_ci_lower_pct,
    cast(null as double) as burden_ci_upper_pct,
    rank() over (
        partition by f.basket_id, p.percentile
        order by (4.0 * f.basket_cost_2024 / p.income) desc
    ) as rank_burden,
    f.thin_coverage_flag
from fact_basket_state as f
join fact_percentile as p on p.state = f.state and p.year = 2024
where p.percentile in (10, 20, 40, 50);

-- Q2. How much of the gap between states comes from prices, and how much from incomes?
-- ln(burden) = ln(price) - ln(income), so
-- Var(ln burden) = [Var(ln p) - Cov(ln p, ln y)] + [Var(ln y) - Cov(ln p, ln y)]
create or replace table mart_decomposition as
with state_logs as (
    select
        f.basket_id,
        p.percentile,
        f.state,
        ln(f.basket_cost_2024) as ln_p,
        ln(p.income)           as ln_y,
        ln(f.basket_cost_2024) - ln(p.income) as ln_b
    from fact_basket_state as f
    join fact_percentile as p on p.state = f.state and p.year = 2024
    where p.percentile in (10, 20, 40, 50)
),
stats as (
    select
        basket_id,
        percentile,
        var_samp(ln_b) as var_ln_b,
        var_samp(ln_p) as var_ln_p,
        var_samp(ln_y) as var_ln_y,
        covar_samp(ln_p, ln_y) as cov_ln_p_y
    from state_logs
    group by basket_id, percentile
)
select
    basket_id,
    percentile,
    round(var_ln_b, 5) as var_log_burden,
    round(var_ln_p, 5) as var_log_price,
    round(var_ln_y, 5) as var_log_income,
    round(cov_ln_p_y, 5) as cov_price_income,
    round(100.0 * (var_ln_p - cov_ln_p_y) / var_ln_b, 2) as share_due_to_price_pct,
    round(100.0 * (var_ln_y - cov_ln_p_y) / var_ln_b, 2) as share_due_to_income_pct,
    round(100.0 * ((var_ln_p - cov_ln_p_y) + (var_ln_y - cov_ln_p_y)) / var_ln_b, 2) as sum_shares_pct
from stats;

-- Q3. What would each state's burden be with typical prices, or with Malaysia's income?
create or replace table mart_counterfactual as
with reference_cost as (
    select
        basket_id,
        round(exp(avg(ln(basket_cost_2024))), 2) as unweighted_state_geomean_cost_2024
    from fact_basket_state
    group by basket_id
),
reference_income as (
    select percentile, income as mys_income_2024
    from ref_malaysia_percentile
    where year = 2024 and percentile in (10, 20, 40, 50)
)
select
    b.state,
    b.basket_id,
    b.percentile,
    b.burden_pct as actual_burden_pct,
    round(4.0 * rc.unweighted_state_geomean_cost_2024 / b.income_2024 * 100, 2) as typical_price_burden_pct,
    round(4.0 * b.basket_cost_2024 / ri.mys_income_2024 * 100, 2) as mys_income_burden_pct,
    round((4.0 * rc.unweighted_state_geomean_cost_2024 / b.income_2024 * 100) - b.burden_pct, 2) as effect_typical_price_pts,
    round((4.0 * b.basket_cost_2024 / ri.mys_income_2024 * 100) - b.burden_pct, 2) as effect_mys_income_pts
from mart_burden as b
join reference_cost as rc on rc.basket_id = b.basket_id
join reference_income as ri on ri.percentile = b.percentile;

-- Q4. Did median income beat prices between the 2022 and 2024 surveys?
create or replace table mart_real_income as
with inc as (
    select
        state,
        max(income_median) filter (where year = 2022) as inc_median_2022,
        max(income_median) filter (where year = 2024) as inc_median_2024
    from fact_state_year
    group by state
),
cpi_g as (
    select
        state,
        avg(cpi_index) filter (where year(month) = 2024 and division = 'overall') /
        avg(cpi_index) filter (where year(month) = 2022 and division = 'overall') as cpi_overall_ratio,
        avg(cpi_index) filter (where year(month) = 2024 and division = '01') /
        avg(cpi_index) filter (where year(month) = 2022 and division = '01') as cpi_food_ratio
    from fact_cpi_month
    group by state
)
select
    inc.state,
    inc.inc_median_2022,
    inc.inc_median_2024,
    round(100.0 * (inc.inc_median_2024 / inc.inc_median_2022 - 1), 1) as nom_median_growth_pct,
    round(100.0 * (cg.cpi_overall_ratio - 1), 1) as cpi_overall_growth_pct,
    round(100.0 * (cg.cpi_food_ratio - 1), 1) as cpi_food_growth_pct,
    round(100.0 * ((inc.inc_median_2024 / inc.inc_median_2022) / cg.cpi_overall_ratio - 1), 1) as real_median_growth_pct
from inc
join cpi_g as cg on cg.state = inc.state;

-- Sensitivity to the purchase assumption
create or replace table mart_sensitivity as
select
    f.state,
    f.basket_id,
    p.percentile,
    q.purchases_per_month,
    round(q.purchases_per_month * f.basket_cost_2024, 2) as monthly_basket_spend,
    p.income as income_2024,
    round(q.purchases_per_month * f.basket_cost_2024 / p.income * 100, 2) as burden_pct
from fact_basket_state as f
join fact_percentile as p on p.state = f.state and p.year = 2024
cross join (values (2), (4), (6)) as q(purchases_per_month)
where p.percentile in (10, 20, 40, 50);

-- Does the choice of basket change who ranks worst? Spearman across basket pairs.
-- The purchase count cannot change ranks, because it scales every state equally.
create or replace table mart_rank_stability as
with ranked as (
    select
        basket_id,
        percentile,
        state,
        burden_pct,
        row_number() over (partition by basket_id, percentile order by burden_pct) as rn
    from mart_burden
),
avg_ranked as (
    select
        basket_id,
        percentile,
        state,
        avg(rn) over (partition by basket_id, percentile, burden_pct) as avg_rank
    from ranked
),
paired as (
    select
        a.percentile,
        a.basket_id as basket_a,
        b.basket_id as basket_b,
        a.avg_rank as rank_a,
        b.avg_rank as rank_b
    from avg_ranked as a
    join avg_ranked as b
      on a.state = b.state
     and a.percentile = b.percentile
     and a.basket_id < b.basket_id
)
select
    percentile,
    basket_a || ' vs ' || basket_b as basket_pair,
    round(corr(rank_a, rank_b), 4) as spearman_rank_corr
from paired
group by percentile, basket_a, basket_b
order by percentile, basket_pair;

-- Q5. Have formal wages kept up since the survey? Twelve-month windows, because the
-- monthly median is noisy and rounded.
create or replace table mart_real_wages as
with wage_windows as (
    select
        state,
        median(wages_median) filter (where month between date '2022-07-01' and date '2023-06-01') as wage_median_start,
        median(wages_median) filter (where month between date '2025-07-01' and date '2026-06-01') as wage_median_end
    from fact_wage_month
    group by state
),
cpi_windows as (
    select
        state,
        avg(cpi_index) filter (where month between date '2022-07-01' and date '2023-06-01') as cpi_start,
        avg(cpi_index) filter (where month between date '2025-07-01' and date '2026-06-01') as cpi_end
    from fact_cpi_month
    where division = 'overall'
    group by state
)
select
    w.state,
    w.wage_median_start,
    w.wage_median_end,
    round(100.0 * (w.wage_median_end / w.wage_median_start - 1), 1) as nom_wage_growth_pct,
    round(100.0 * (c.cpi_end / c.cpi_start - 1), 1) as cpi_growth_pct,
    round(100.0 * ((w.wage_median_end / w.wage_median_start) / (c.cpi_end / c.cpi_start) - 1), 1) as real_wage_growth_pct
from wage_windows as w
join cpi_windows as c on c.state = w.state;

-- Q6. What share of ALL households in a state earn less than a household-type budget?
-- This is not the share of households of that type.
create or replace table mart_budget_gap as
with city_map as (
    select trim(city) as city, trim(state) as state
    from read_csv('data/seed/belanjawanku_city_state.csv', header = true)
),
budgets as (
    select trim(city) as city, trim(household_type) as household_type, cast(budget_rm as double) as budget_rm
    from read_csv('data/seed/belanjawanku_2024_25.csv', header = true)
),
state_median as (
    select state, income as median_income
    from fact_percentile
    where year = 2024 and percentile = 50
)
select
    m.state,
    b.city,
    b.household_type,
    b.budget_rm,
    count(p.percentile) as pct_households_below,
    sm.median_income,
    round(100.0 * b.budget_rm / sm.median_income, 1) as budget_pct_of_median
from budgets as b
join city_map as m on m.city = b.city
join state_median as sm on sm.state = m.state
left join fact_percentile as p
  on p.state = m.state and p.year = 2024 and p.income < b.budget_rm
group by m.state, b.city, b.household_type, b.budget_rm, sm.median_income;

-- Q7. How far above the official poverty line do lower-income households sit?
create or replace table mart_pli as
select
    p.state,
    p.pli_2022,
    p.pli_2024,
    round(100.0 * (p.pli_2024 / p.pli_2022 - 1), 1) as pli_growth_pct,
    p10.income as income_p10,
    p20.income as income_p20,
    round(p10.income / p.pli_2024, 2) as p10_multiple_of_pli,
    s.poverty_rate as poverty_rate_2024
from fact_pli as p
join fact_percentile as p10 on p10.state = p.state and p10.year = 2024 and p10.percentile = 10
join fact_percentile as p20 on p20.state = p.state and p20.year = 2024 and p20.percentile = 20
join fact_state_year as s on s.state = p.state and s.year = 2024;

-- Q8. Who shows up under pressure on several independent measures? No composite index:
-- a signal is a top-four rank (1 = most pressure) on one measure.
create or replace table mart_pressure as
with burden_ranks as (
    select state, rank_burden as rank_p10_burden
    from mart_burden
    where basket_id = 'staples_plus_rice' and percentile = 10
),
spending_ranks as (
    select state, rank() over (order by exp_share_mean_pct desc) as rank_exp_share
    from fact_state_year
    where year = 2024
),
budget_ranks as (
    select state, rank() over (order by pct_households_below desc) as rank_budget_gap
    from mart_budget_gap
    where household_type = 'Married (2 Children)'
),
poverty_ranks as (
    select state, rank() over (order by poverty_rate desc) as rank_poverty
    from fact_state_year
    where year = 2024
),
growth_ranks as (
    select state, rank() over (order by real_median_growth_pct asc) as rank_real_income_growth
    from mart_real_income
)
select
    ds.state,
    p.rank_p10_burden,
    e.rank_exp_share,
    b.rank_budget_gap,
    v.rank_poverty,
    g.rank_real_income_growth,
    case when b.rank_budget_gap is null then 4 else 5 end as signals_available,
    (p.rank_p10_burden <= 4)::int
      + (e.rank_exp_share <= 4)::int
      + coalesce((b.rank_budget_gap <= 4)::int, 0)
      + (v.rank_poverty <= 4)::int
      + (g.rank_real_income_growth <= 4)::int as pressure_signals
from dim_state as ds
join burden_ranks as p on p.state = ds.state
join spending_ranks as e on e.state = ds.state
left join budget_ranks as b on b.state = ds.state
join poverty_ranks as v on v.state = ds.state
join growth_ranks as g on g.state = ds.state;

create or replace table quality_audit as
select 1 as step, 'Coverage' as category, 'States and territories in dim_state' as rule_description,
       16 as expected_value, count(*) as actual_value
from dim_state
union all
select 2, 'Coverage', 'Districts in dim_district (2024)', 162, count(*)
from dim_district
union all
select 3, 'Reconciliation', 'Malaysia 2024 median income matches the published RM7,017',
       7017, cast(income_median as bigint)
from ref_malaysia_year where year = 2024
union all
select 4, 'Reconciliation', 'Malaysia 2024 poverty line matches the published RM2,705',
       2705, cast(pli as bigint)
from ref_malaysia_year where year = 2024
union all
select 5, 'Completeness', 'State-basket pairs in fact_basket_state', 48, count(*)
from fact_basket_state
union all
select 6, 'Completeness', 'State-group pairs in fact_spending_state', 208, count(*)
from fact_spending_state
union all
select 7, 'Method', 'Basket price rows read from PriceCatcher', count(*), count(*)
from stg_basket_price;
