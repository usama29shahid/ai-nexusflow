{{ config(materialized="view") }}

with src as (
    select * from {{ iceberg_catalog() }}.raw_dlt_smoke.smoke
)

select
    id as smoke_id,
    name as smoke_name,
    run_id,
    _extracted_at,
    _dlt_load_id,
    _dlt_id,
    concat(cast(id as string), '|', run_id) as smoke_row_key
from src
