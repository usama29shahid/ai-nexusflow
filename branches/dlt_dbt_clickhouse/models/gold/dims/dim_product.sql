{{
  config(
    alias="dim_product",
    materialized="incremental",
    incremental_strategy="delete+insert",
    unique_key="dim_product_sk",
  )
}}

{# SCD2 Pattern A: change/reappear use scd_bound_at; first-ever key uses source_created_at. #}

{% if not is_incremental() %}

with silver as (
    select
        product_id,
        pk_hash,
        row_hash,
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
        _extracted_at
    from {{ ref("stg_route__products") }}
)

select
    {{ dbt_utils.generate_surrogate_key([
        "product_id",
        "row_hash",
        "toString(coalesce(source_created_at, cast('1900-01-01 00:00:00.000' as DateTime64(3, 'UTC'))))"
    ]) }} as dim_product_sk,
    product_id,
    pk_hash,
    row_hash,
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
    coalesce(source_created_at, {{ scd2_valid_from_unknown() }}) as valid_from,
    {{ scd2_valid_to_open() }} as valid_to,
    cast(1 as Int8) as is_active,
    cast(0 as Int8) as is_deleted,
    now64(3) as inserted_at,
    now64(3) as updated_at
from silver

{% else %}

with silver as (
    select
        product_id,
        pk_hash,
        row_hash,
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
        _extracted_at
    from {{ ref("stg_route__products") }}
),

current_gold as (
    select *
    from {{ this }}
    where is_active = 1
),

new_rows as (
    select s.*
    from silver as s
    left anti join current_gold as g
        on s.pk_hash = g.pk_hash
),

gold_keys as (
    select distinct pk_hash
    from {{ this }}
),

truly_new as (
    select n.*
    from new_rows as n
    left anti join gold_keys as k
        on n.pk_hash = k.pk_hash
),

reappear_rows as (
    select n.*
    from new_rows as n
    inner join gold_keys as k
        on n.pk_hash = k.pk_hash
),

deleted_rows as (
    select g.*
    from current_gold as g
    left anti join silver as s
        on g.pk_hash = s.pk_hash
),

changed_rows as (
    select
        s.*,
        g.dim_product_sk as existing_sk,
        g.valid_from as existing_valid_from,
        g.inserted_at as existing_inserted_at
    from silver as s
    inner join current_gold as g
        on s.pk_hash = g.pk_hash
    where s.row_hash != g.row_hash
),

expired_deleted as (
    select
        dim_product_sk,
        product_id,
        pk_hash,
        row_hash,
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
        valid_from,
        {{ scd2_bound_at() }} as valid_to,
        cast(0 as Int8) as is_active,
        cast(1 as Int8) as is_deleted,
        inserted_at,
        {{ scd2_bound_at() }} as updated_at
    from deleted_rows
),

expired_changed as (
    select
        existing_sk as dim_product_sk,
        g.product_id,
        g.pk_hash,
        g.row_hash,
        g.title,
        g.slug,
        g.description,
        g.quantity,
        g.sold,
        g.price,
        g.price_after_discount,
        g.has_discount,
        g.discount_amount,
        g.image_cover,
        g.ratings_average,
        g.ratings_quantity,
        g.brand_id,
        g.brand_name,
        g.brand_slug,
        g.brand_image,
        g.category_id,
        g.category_name,
        g.category_slug,
        g.category_image,
        g.source_created_at,
        g.source_updated_at,
        g.run_id,
        existing_valid_from as valid_from,
        {{ scd2_bound_at() }} as valid_to,
        cast(0 as Int8) as is_active,
        cast(0 as Int8) as is_deleted,
        existing_inserted_at as inserted_at,
        {{ scd2_bound_at() }} as updated_at
    from changed_rows as c
    inner join current_gold as g
        on c.existing_sk = g.dim_product_sk
),

new_versions as (
    select
        {{ dbt_utils.generate_surrogate_key([
            "product_id",
            "row_hash",
            "toString(coalesce(source_created_at, cast('1900-01-01 00:00:00.000' as DateTime64(3, 'UTC'))))"
        ]) }} as dim_product_sk,
        product_id,
        pk_hash,
        row_hash,
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
        coalesce(source_created_at, {{ scd2_valid_from_unknown() }}) as valid_from,
        {{ scd2_valid_to_open() }} as valid_to,
        cast(1 as Int8) as is_active,
        cast(0 as Int8) as is_deleted,
        {{ scd2_bound_at() }} as inserted_at,
        {{ scd2_bound_at() }} as updated_at
    from truly_new

    union all

    select
        {{ dbt_utils.generate_surrogate_key([
            "product_id",
            "row_hash",
            "toString(" ~ scd2_bound_at() ~ ")"
        ]) }} as dim_product_sk,
        product_id,
        pk_hash,
        row_hash,
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
        {{ scd2_bound_at() }} as valid_from,
        {{ scd2_valid_to_open() }} as valid_to,
        cast(1 as Int8) as is_active,
        cast(0 as Int8) as is_deleted,
        {{ scd2_bound_at() }} as inserted_at,
        {{ scd2_bound_at() }} as updated_at
    from (
        select
            product_id,
            pk_hash,
            row_hash,
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
            run_id
        from reappear_rows
        union all
        select
            product_id,
            pk_hash,
            row_hash,
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
            run_id
        from changed_rows
    ) as scd_bound_opens
)

select * from expired_deleted
union all
select * from expired_changed
union all
select * from new_versions

{% endif %}
