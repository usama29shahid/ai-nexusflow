{% macro generate_schema_name(custom_schema_name, node) -%}
    {#- Iceberg schemas are layer names (stg_dlt_smoke, gold). Do not prefix with target.schema. -#}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
