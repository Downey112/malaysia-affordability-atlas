-- 01_staging.sql
-- Clean raw tables and build the single source of basket prices.

create or replace table stg_dosm_hies_state as
select
    trim(state)                      as state,
    year(cast(date as date))         as survey_year,
    cast(income_mean as double)      as income_mean,
    cast(income_median as double)    as income_median,
    cast(expenditure_mean as double) as expenditure_mean,
    cast(gini as double)             as gini,
    cast(poverty as double)          as poverty_rate
from read_parquet('data/raw/hies_state.parquet');

-- 2024 only: district names differ between the 2022 and 2024 releases
create or replace table stg_dosm_hies_district as
select
    trim(state) || ' | ' || trim(district) as district_key,
    trim(state)                      as state,
    trim(district)                   as district,
    year(cast(date as date))         as survey_year,
    cast(income_mean as double)      as income_mean,
    cast(income_median as double)    as income_median,
    cast(expenditure_mean as double) as expenditure_mean,
    cast(gini as double)             as gini,
    cast(poverty as double)          as poverty_rate
from read_parquet('data/raw/hies_district.parquet')
where year(cast(date as date)) = 2024;

-- 'maximum' at percentile p is the p-th percentile cut-off. P100 has no maximum.
create or replace table stg_dosm_percentile_state as
select
    trim(state)                 as state,
    year(cast(date as date))    as survey_year,
    cast(percentile as integer) as percentile,
    cast(income as double)      as income
from read_parquet('data/raw/hies_state_percentile.parquet')
where trim(variable) = 'maximum' and percentile <= 99;

create or replace table stg_dosm_cpi as
select
    trim(state)           as state,
    cast(date as date)    as month,
    trim(division)        as division,
    cast(index as double) as cpi_index
from read_parquet('data/raw/cpi_2d_state.parquet')
where division in ('overall', '01')
  and cast(date as date) >= date '2022-01-01';

create or replace table stg_dosm_formal_wages as
select
    trim(state)                  as state,
    cast(date as date)           as month,
    cast(employees as bigint)    as employees,
    cast(wages_median as double) as wages_median
from read_parquet('data/raw/formal_wages_state.parquet')
where trim(state) <> 'Malaysia';

create or replace table stg_dosm_poverty as
select
    trim(state)                      as state,
    year(cast(date as date))         as survey_year,
    cast(poverty_absolute as double) as poverty_absolute,
    cast(poverty_hardcore as double) as poverty_hardcore,
    cast(poverty_relative as double) as poverty_relative
from read_parquet('data/raw/hh_poverty_state.parquet');

create or replace table stg_dosm_pli as
select
    trim(state)              as state,
    cast(pli_2022 as double) as pli_2022,
    cast(pli_2024 as double) as pli_2024
from read_parquet('data/raw/pli_state.parquet');

create or replace table stg_dosm_spending as
select
    trim(state)               as state,
    trim(group_code)          as group_code,
    trim(group_name_en)       as group_name_en,
    cast(spend_rm as double)  as spend_rm,
    cast(share_pct as double) as share_pct
from read_parquet('data/raw/spending_group_state.parquet');

create or replace table seed_baskets as
select
    trim(basket_id)                        as basket_id,
    cast(nullif(item_code, '') as integer) as item_code,
    nullif(trim(category_rule), '')        as category_rule,
    cast(quantity as double)               as quantity,
    trim(item_name)                        as item_name,
    trim(reason)                           as reason
from read_csv('data/seed/baskets.csv', header = true, all_varchar = true);

-- item_key is the item code, or -1 for rice, which pools every 10 kg BERAS item.
-- Everything downstream, SQL and bootstrap alike, reads prices from this table.
create or replace table stg_basket_price as
with premise as (
    select premise_code, trim(state) as state
    from read_parquet(getvariable('pricecatcher_dir') || '/dim_premise.parquet')
),
item as (
    select item_code, item_category, unit
    from read_parquet(getvariable('pricecatcher_dir') || '/dim_item.parquet')
),
price as (
    select premise_code, item_code, month, cast(price as double) as price
    from read_parquet(getvariable('pricecatcher_dir') || '/fact_price_monthly.parquet')
)
select
    pr.state,
    p.premise_code,
    p.item_code as item_key,
    p.item_code as source_item_code,
    p.month,
    p.price
from price as p
join premise as pr on pr.premise_code = p.premise_code
where p.item_code in (select item_code from seed_baskets where item_code is not null)
union all
select
    pr.state,
    p.premise_code,
    -1 as item_key,
    p.item_code as source_item_code,
    p.month,
    p.price
from price as p
join premise as pr on pr.premise_code = p.premise_code
join item as i on i.item_code = p.item_code
where i.item_category = 'BERAS' and i.unit = '10 kg';

create or replace table stg_ref_malaysia_year as
select
    year(cast(h.date as date))      as year,
    cast(h.income_mean as double)   as income_mean,
    cast(h.income_median as double) as income_median,
    case year(cast(h.date as date))
        when 2022 then p.pli_2022
        when 2024 then p.pli_2024
    end as pli
from read_parquet('data/raw/hh_income.parquet') as h
left join stg_dosm_pli as p on p.state = 'Malaysia'
where year(cast(h.date as date)) in (2022, 2024);

create or replace table stg_ref_malaysia_percentile as
select
    year(cast(date as date))    as year,
    cast(percentile as integer) as percentile,
    cast(income as double)      as income
from read_parquet('data/raw/hies_malaysia_percentile.parquet')
where trim(variable) = 'maximum' and percentile <= 99;
