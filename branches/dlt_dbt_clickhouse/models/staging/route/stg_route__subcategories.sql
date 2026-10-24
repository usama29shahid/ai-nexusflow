{{
  config(
    alias="stg_route__subcategories",
  )
}}

{# FULL_LOAD silver: lookback / --full-refresh / optional run_id; dedupe by pk_hash. docs/dbt-modeling.md #}

with src as (
    select * from {{ source("route_raw", "subcategories") }}
),

scoped as (
    select *
    from src
    where
        {% if flags.FULL_REFRESH %}
            1 = 1
        {% elif var("run_id", none) %}
            run_id = '{{ var("run_id") }}'
        {% else %}
            _extracted_at >= now64(3) - interval {{ var("lookback_days", 15) }} day
        {% endif %}
),

renamed as (
    select
        cast(_id as String) as subcategory_id,
        cast(name as String) as name,
        cast(slug as Nullable(String)) as slug,
        cast(category as String) as category_id,
        cast(created_at as DateTime64(3, 'UTC')) as source_created_at,
        cast(updated_at as DateTime64(3, 'UTC')) as source_updated_at,
        cast(run_id as String) as run_id,
        cast(_extracted_at as DateTime64(3, 'UTC')) as _extracted_at,
        cast(_source as String) as _source,
        cast(_endpoint as String) as _endpoint,
        cast(_nexus_env as String) as _nexus_env,
        cast(_dlt_load_id as String) as _dlt_load_id,
        cast(_dlt_id as String) as _dlt_id
    from scoped
),

keyed as (
    select
        *,
        {{ dbt_utils.generate_surrogate_key(["subcategory_id"]) }} as pk_hash,
        {{ dbt_utils.generate_surrogate_key([
            "coalesce(name, '')",
            "coalesce(slug, '')",
            "coalesce(category_id, '')"
        ]) }} as row_hash,
        {{ dbt_utils.generate_surrogate_key(["subcategory_id", "run_id"]) }} as ingestion_hash,
        now64(3) as _inserted_at
    from renamed
),

deduped as (
    select
        *,
        row_number() over (
            partition by pk_hash
            order by _extracted_at desc, _dlt_id desc
        ) as _dedupe_rn
    from keyed
)

select
    subcategory_id,
    pk_hash,
    row_hash,
    ingestion_hash,
    name,
    slug,
    category_id,
    source_created_at,
    source_updated_at,
    run_id,
    _extracted_at,
    _inserted_at,
    _source,
    _endpoint,
    _nexus_env,
    _dlt_load_id,
    _dlt_id
from deduped
where _dedupe_rn = 1
