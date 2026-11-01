-- 03_facts.sql
-- Star schema facts and Malaysia reference tables.

create or replace table fact_state_year as
select
    h.state,
    h.survey_year as year,
    h.income_mean,
    h.income_median,
    h.expenditure_mean,
    round(100.0 * h.expenditure_mean / h.income_mean, 1) as exp_share_mean_pct,
    h.gini,
    h.poverty_rate,
    p.poverty_hardcore,
    p.poverty_relative
from stg_dosm_hies_state as h
left join stg_dosm_poverty as p
  on p.state = h.state and p.survey_year = h.survey_year;

create or replace table fact_district_year as
select
    district_key,
    state,
    district,
    survey_year as year,
    income_mean,
    income_median,
    expenditure_mean,
    round(100.0 * expenditure_mean / income_mean, 1) as exp_share_mean_pct,
    gini,
    poverty_rate
from stg_dosm_hies_district;

create or replace table fact_percentile as
select state, survey_year as year, percentile, income
from stg_dosm_percentile_state;

create or replace table fact_cpi_month as
select state, month, division, cpi_index
from stg_dosm_cpi;

create or replace table fact_wage_month as
select state, month, employees, wages_median
from stg_dosm_formal_wages;

create or replace table fact_pli as
select state, pli_2022, pli_2024
from stg_dosm_pli
where state <> 'Malaysia';

create or replace table fact_spending_state as
select state, group_code, spend_rm, share_pct
from stg_dosm_spending
where state <> 'Malaysia';

create or replace table ref_malaysia_year as
select year, income_mean, income_median, pli
from stg_ref_malaysia_year;

create or replace table ref_malaysia_percentile as
select year, percentile, income
from stg_ref_malaysia_percentile;

create or replace table ref_malaysia_spending as
select group_code, group_name_en, spend_rm, share_pct
from stg_dosm_spending
where state = 'Malaysia';

create or replace table fact_basket_state as
with cpi_factors as (
    select
        state,
        avg(cpi_index) filter (where year(month) = 2024) as cpi_01_2024,
        avg(cpi_index) filter (where month between date '2025-10-01' and date '2026-09-01') as cpi_01_window
    from stg_dosm_cpi
    where division = '01'
    group by state
),
item_prices as (
    select state, item_key, exp(sum(ln(price)) / count(*)) as geom_price
    from stg_basket_price
    group by state, item_key
),
rice_metrics as (
    select
        state,
        count(distinct source_item_code) as rice_items_count,
        count(distinct premise_code) as rice_shops_count
    from stg_basket_price
    where item_key = -1
    group by state
),
basket_calc as (
    select
        ip.state,
        b.basket_id,
        count(*) as items_priced,
        sum(b.quantity * ip.geom_price) as basket_cost_raw
    from seed_baskets as b
    join item_prices as ip
      on ip.item_key = case when b.category_rule = 'BERAS_10KG' then -1 else b.item_code end
    group by ip.state, b.basket_id
)
select
    bc.state,
    bc.basket_id,
    bc.items_priced,
    ds.shops_count,
    round(bc.basket_cost_raw, 2) as basket_cost_raw,
    round(cf.cpi_01_2024, 2)     as cpi_01_2024,
    round(cf.cpi_01_window, 2)   as cpi_01_window,
    cf.cpi_01_2024 / cf.cpi_01_window as cpi_backcast_ratio,
    round(bc.basket_cost_raw * cf.cpi_01_2024 / cf.cpi_01_window, 2) as basket_cost_2024,
    cast(null as double)         as ci_lower,
    cast(null as double)         as ci_upper,
    ds.thin_coverage_flag,
    rm.rice_items_count,
    rm.rice_shops_count
from basket_calc as bc
join cpi_factors as cf on cf.state = bc.state
join dim_state as ds on ds.state = bc.state
join rice_metrics as rm on rm.state = bc.state;
