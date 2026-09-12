{{
  config(
    alias="brg_product_image",
    materialized="incremental",
    incremental_strategy="delete+insert",
    unique_key="brg_product_image_sk",
  )
}}

{% set _ensure_dim_product = ref("dim_product") %}

{# SCD2 Pattern A: first-ever key uses _extracted_at; change/reappear use scd_bound_at.
   Pattern A delete valid_to uses the product's silver extract when a sibling row exists
   (membership replace seam), else scd_bound_at (full wipe). #}

{% if not is_incremental() %}

with silver as (
    select
        product_id,
        image_url,
        list_idx,
        pk_hash,
        row_hash,
        run_id,
        _extracted_at
    from {{ ref("stg_route__products__images") }}
)

select
    {{ dbt_utils.generate_surrogate_key([
        "product_id",
        "row_hash",
        "toString(_extracted_at)"
    ]) }} as brg_product_image_sk,
    product_id,
    image_url,
    list_idx,
    pk_hash,
    row_hash,
    run_id,
    _extracted_at as valid_from,
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
        image_url,
        list_idx,
        pk_hash,
        row_hash,
        run_id,
        _extracted_at
    from {{ ref("stg_route__products__images") }}
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

product_extract as (
    select
        product_id,
        max(_extracted_at) as extract_at
    from silver
    group by product_id
),

changed_rows as (
    select
        s.*,
        g.brg_product_image_sk as existing_sk,
        g.valid_from as existing_valid_from,
        g.inserted_at as existing_inserted_at,
        g.product_id as g_product_id,
        g.image_url as g_image_url,
        g.list_idx as g_list_idx,
        g.pk_hash as g_pk_hash,
        g.row_hash as g_row_hash,
        g.run_id as g_run_id
    from silver as s
    inner join current_gold as g
        on s.pk_hash = g.pk_hash
    where s.row_hash != g.row_hash
),

expired_deleted as (
    select
        d.brg_product_image_sk,
        d.product_id,
        d.image_url,
        d.list_idx,
        d.pk_hash,
        d.row_hash,
        d.run_id,
        d.valid_from,
        if(pe.product_id = d.product_id, pe.extract_at, {{ scd2_bound_at() }}) as valid_to,
        cast(0 as Int8) as is_active,
        cast(1 as Int8) as is_deleted,
        d.inserted_at,
        {{ scd2_bound_at() }} as updated_at
    from deleted_rows as d
    left join product_extract as pe
        on d.product_id = pe.product_id
),

expired_changed as (
    select
        existing_sk as brg_product_image_sk,
        g_product_id as product_id,
        g_image_url as image_url,
        g_list_idx as list_idx,
        g_pk_hash as pk_hash,
        g_row_hash as row_hash,
        g_run_id as run_id,
        existing_valid_from as valid_from,
        {{ scd2_bound_at() }} as valid_to,
        cast(0 as Int8) as is_active,
        cast(0 as Int8) as is_deleted,
        existing_inserted_at as inserted_at,
        {{ scd2_bound_at() }} as updated_at
    from changed_rows
),

new_versions as (
    select
        {{ dbt_utils.generate_surrogate_key([
            "product_id",
            "row_hash",
            "toString(_extracted_at)"
        ]) }} as brg_product_image_sk,
        product_id,
        image_url,
        list_idx,
        pk_hash,
        row_hash,
        run_id,
        _extracted_at as valid_from,
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
        ]) }} as brg_product_image_sk,
        product_id,
        image_url,
        list_idx,
        pk_hash,
        row_hash,
        run_id,
        {{ scd2_bound_at() }} as valid_from,
        {{ scd2_valid_to_open() }} as valid_to,
        cast(1 as Int8) as is_active,
        cast(0 as Int8) as is_deleted,
        {{ scd2_bound_at() }} as inserted_at,
        {{ scd2_bound_at() }} as updated_at
    from (
        select product_id, image_url, list_idx, pk_hash, row_hash, run_id
        from reappear_rows
        union all
        select product_id, image_url, list_idx, pk_hash, row_hash, run_id
        from changed_rows
    ) as scd_bound_opens
)

select * from expired_deleted
union all
select * from expired_changed
union all
select * from new_versions

{% endif %}
