-- 02_dimensions.sql
-- Conformed dimensions for the star schema.

create or replace table dim_state as
with premise_summary as (
    select
        trim(state) as state,
        trim(region) as region,
        count(distinct premise_code) as shops_count
    from read_parquet(getvariable('pricecatcher_dir') || '/dim_premise.parquet')
    group by trim(state), trim(region)
)
select
    s.state,
    p.region,
    s.state like 'W.P.%' as is_federal_territory,
    p.shops_count,
    p.shops_count < 30 as thin_coverage_flag
from (select distinct state from stg_dosm_hies_state) as s
join premise_summary as p on p.state = s.state;

create or replace table dim_district as
select distinct
    district_key,
    state,
    district
from stg_dosm_hies_district
order by state, district;

create or replace table dim_year as
select
    year_val as year,
    year_val in (2019, 2022, 2024) as has_percentiles
from (values (2019), (2022), (2024)) as y(year_val);

create or replace table dim_month as
select distinct
    month,
    year(month) as year,
    month(month) as month_number,
    month between date '2025-10-01' and date '2026-09-01' as is_price_window
from stg_dosm_cpi
order by month;

create or replace table dim_basket as
select
    basket_id,
    case basket_id
        when 'core' then 'Core 7 (with rice)'
        when 'staples_16' then 'Staples 16 (no rice)'
        when 'staples_plus_rice' then 'Staples + rice (17 items)'
    end as basket_name,
    case basket_id
        when 'core' then 1
        when 'staples_16' then 2
        when 'staples_plus_rice' then 3
    end as basket_order,
    count(*) as items_count,
    bool_or(category_rule = 'BERAS_10KG') as has_rice,
    case basket_id
        when 'core' then 'Rice, chicken, eggs, ikan kembung, cooking oil, sugar and onions'
        when 'staples_16' then 'The 16 staples used in the PriceCatcher Retail Pricing project'
        when 'staples_plus_rice' then 'The 16 staples plus 10 kg of rice'
    end as description
from seed_baskets
group by basket_id;

create or replace table dim_percentile as
select
    cast(p_val as integer) as percentile,
    'P' || cast(p_val as varchar) as percentile_label,
    p_val in (10, 20, 40, 50) as is_reporting_band
from range(1, 100) as p(p_val);

create or replace table dim_spending_group as
select
    group_code,
    min(group_name_en) as group_name_en
from stg_dosm_spending
group by group_code
order by group_code;
