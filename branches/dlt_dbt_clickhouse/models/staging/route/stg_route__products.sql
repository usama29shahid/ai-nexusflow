{{
  config(
    alias="stg_route__products",
  )
}}

{# FULL_LOAD silver: lookback / --full-refresh / optional run_id; dedupe by pk_hash. docs/dbt-modeling.md #}

with src as (
    select * from {{ source("route_raw", "products") }}
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
        cast(id as String) as product_id,
        cast(title as String) as title,
        cast(slug as Nullable(String)) as slug,
        cast(description as Nullable(String)) as description,
        cast(quantity as Int64) as quantity,
        cast(sold as Int64) as sold,
        cast(price as Float64) as price,
        cast(price_after_discount as Nullable(Float64)) as price_after_discount,
        cast(image_cover as Nullable(String)) as image_cover,
        cast(ratings_average as Nullable(Float64)) as ratings_average,
        cast(ratings_quantity as Nullable(Int64)) as ratings_quantity,
        cast(brand___id as Nullable(String)) as brand_id,
        cast(brand__name as Nullable(String)) as brand_name,
        cast(brand__slug as Nullable(String)) as brand_slug,
        cast(brand__image as Nullable(String)) as brand_image,
        cast(category___id as Nullable(String)) as category_id,
        cast(category__name as Nullable(String)) as category_name,
        cast(category__slug as Nullable(String)) as category_slug,
        cast(category__image as Nullable(String)) as category_image,
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
        {{ dbt_utils.generate_surrogate_key(["product_id"]) }} as pk_hash,
        {{ dbt_utils.generate_surrogate_key([
            "coalesce(title, '')",
            "coalesce(slug, '')",
            "coalesce(description, '')",
            "coalesce(toString(quantity), '')",
            "coalesce(toString(sold), '')",
            "coalesce(toString(price), '')",
            "coalesce(toString(price_after_discount), '')",
            "coalesce(image_cover, '')",
            "coalesce(toString(ratings_average), '')",
            "coalesce(toString(ratings_quantity), '')",
            "coalesce(brand_id, '')",
            "coalesce(brand_name, '')",
            "coalesce(brand_slug, '')",
            "coalesce(brand_image, '')",
            "coalesce(category_id, '')",
            "coalesce(category_name, '')",
            "coalesce(category_slug, '')",
            "coalesce(category_image, '')"
        ]) }} as row_hash,
        {{ dbt_utils.generate_surrogate_key(["product_id", "run_id"]) }} as ingestion_hash,
        (
            price_after_discount is not null
            and price_after_discount < price
        ) as has_discount,
        if(
            price_after_discount is not null and price_after_discount < price,
            price - price_after_discount,
            cast(0 as Float64)
        ) as discount_amount,
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
    product_id,
    pk_hash,
    row_hash,
    ingestion_hash,
    title,
    slug,
    description,
    quantity,
    sold,
    price,
    price_after_discount,
    has_discount,
    discount_amount,
    image_cover,
    ratings_average,
    ratings_quantity,
    brand_id,
    brand_name,
    brand_slug,
    brand_image,
    category_id,
    category_name,
    category_slug,
    category_image,
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
