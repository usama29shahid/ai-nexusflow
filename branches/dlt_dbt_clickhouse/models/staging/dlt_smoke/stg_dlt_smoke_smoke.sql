{{ config(materialized="view") }}

with src as (
    select * from {{ source("dlt_smoke_raw", "smoke") }}
)

select
    id as smoke_id,
    name as smoke_name,
    run_id,
    _extracted_at,
    _dlt_load_id,
    _dlt_id,
    concat(toString(id), '|', run_id) as smoke_row_key
from src
