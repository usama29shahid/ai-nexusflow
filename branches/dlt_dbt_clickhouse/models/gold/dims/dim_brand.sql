{{
  config(
    alias="dim_brand",
    materialized="incremental",
    incremental_strategy="delete+insert",
    unique_key="dim_brand_sk",
  )
}}

{# SCD2 Pattern A: change/reappear use scd_bound_at; first-ever key uses source_created_at. #}

{% if not is_incremental() %}

with silver as (
    select
        brand_id,
        pk_hash,
        row_hash,
        name,
        slug,
        image,
        source_created_at,
        source_updated_at,
        run_id,
        _extracted_at
    from {{ ref("stg_route__brands") }}
)

select
    {{ dbt_utils.generate_surrogate_key([
        "brand_id",
        "row_hash",
        "toString(coalesce(source_created_at, cast('1900-01-01 00:00:00.000' as DateTime64(3, 'UTC'))))"
    ]) }} as dim_brand_sk,
    brand_id,
    pk_hash,
    row_hash,
    name,
    slug,
    image,
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
        brand_id,
        pk_hash,
        row_hash,
        name,
        slug,
        image,
        source_created_at,
        source_updated_at,
        run_id,
        _extracted_at
    from {{ ref("stg_route__brands") }}
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
        g.dim_brand_sk as existing_sk,
        g.valid_from as existing_valid_from,
        g.inserted_at as existing_inserted_at
    from silver as s
    inner join current_gold as g
        on s.pk_hash = g.pk_hash
    where s.row_hash != g.row_hash
),

expired_deleted as (
    select
        dim_brand_sk,
        brand_id,
        pk_hash,
        row_hash,
        name,
        slug,
        image,
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
        existing_sk as dim_brand_sk,
        g.brand_id,
        g.pk_hash,
        g.row_hash,
        g.name,
        g.slug,
        g.image,
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
        on c.existing_sk = g.dim_brand_sk
),

new_versions as (
    select
        {{ dbt_utils.generate_surrogate_key([
        "brand_id",
        "row_hash",
        "toString(coalesce(source_created_at, cast('1900-01-01 00:00:00.000' as DateTime64(3, 'UTC'))))"
    ]) }} as dim_brand_sk,
        brand_id,
        pk_hash,
        row_hash,
        name,
        slug,
        image,
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
            "brand_id",
            "row_hash",
            "toString(" ~ scd2_bound_at() ~ ")"
        ]) }} as dim_brand_sk,
        brand_id,
        pk_hash,
        row_hash,
        name,
        slug,
        image,
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
            brand_id,
            pk_hash,
            row_hash,
            name,
            slug,
            image,
            source_created_at,
            source_updated_at,
            run_id
        from reappear_rows
        union all
        select
            brand_id,
            pk_hash,
            row_hash,
            name,
            slug,
            image,
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
