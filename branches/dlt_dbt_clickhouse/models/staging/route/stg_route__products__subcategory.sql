{{
  config(
    alias="stg_route__products__subcategory",
  )
}}
{# FULL_LOAD peer silver: same parent Bronze scope as products; children of winning parents only. #}

with products as (
    select * from {{ source("route_raw", "products") }}
),

scoped_products as (
    select *
    from products
    where
        {% if flags.FULL_REFRESH %}
            1 = 1
        {% elif var("run_id", none) %}
            run_id = '{{ var("run_id") }}'
        {% else %}
            _extracted_at >= now64(3) - interval {{ var("lookback_days", 15) }} day
        {% endif %}
),

parents_keyed as (
    select
        _dlt_id as parent_dlt_id,
        cast(id as String) as product_id,
        cast(run_id as String) as run_id,
        cast(_extracted_at as DateTime64(3, 'UTC')) as _extracted_at,
        {{ dbt_utils.generate_surrogate_key(["cast(id as String)"]) }} as pk_hash
    from scoped_products
),

winning_parents as (
    select
        parent_dlt_id,
        product_id,
        run_id,
        _extracted_at,
        pk_hash,
        row_number() over (
            partition by pk_hash
            order by _extracted_at desc, parent_dlt_id desc
        ) as _dedupe_rn
    from parents_keyed
),

parents as (
    select parent_dlt_id, product_id, run_id, _extracted_at
    from winning_parents
    where _dedupe_rn = 1
),

subcategory as (
    select * from {{ source("route_raw", "products__subcategory") }}
),

joined as (
    select
        cast(p.product_id as String) as product_id,
        cast(s._id as String) as subcategory_id,
        cast(s.name as Nullable(String)) as subcategory_name,
        cast(s.slug as Nullable(String)) as subcategory_slug,
        cast(s.category as Nullable(String)) as parent_category_id,
        cast(s._dlt_list_idx as Int64) as list_idx,
        cast(s._dlt_parent_id as String) as _dlt_parent_id,
        cast(s._dlt_id as String) as _dlt_id,
        cast(p.run_id as String) as run_id,
        cast(p._extracted_at as DateTime64(3, 'UTC')) as _extracted_at,
        {{ dbt_utils.generate_surrogate_key(["p.product_id", "s._id", "s._dlt_list_idx"]) }} as pk_hash,
        {{ dbt_utils.generate_surrogate_key([
            "coalesce(s.name, '')",
            "coalesce(s.slug, '')",
            "coalesce(s.category, '')"
        ]) }} as row_hash,
        {{ dbt_utils.generate_surrogate_key(["p.product_id", "s._id", "s._dlt_list_idx", "p.run_id"]) }} as ingestion_hash,
        now64(3) as _inserted_at
    from subcategory as s
    inner join parents as p
        on s._dlt_parent_id = p.parent_dlt_id
),

deduped as (
    select
        *,
        row_number() over (
            partition by pk_hash
            order by _extracted_at desc, _dlt_id desc
        ) as _dedupe_rn
    from joined
)

select
    product_id,
    subcategory_id,
    subcategory_name,
    subcategory_slug,
    parent_category_id,
    list_idx,
    _dlt_parent_id,
    _dlt_id,
    run_id,
    _extracted_at,
    pk_hash,
    row_hash,
    ingestion_hash,
    _inserted_at
from deduped
where _dedupe_rn = 1
