{% macro generate_schema_name(custom_schema_name, node) -%}
    {#- ClickHouse has no schemas: +schema is the database. Do not prefix with target.schema (warehouse). -#}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name }}_{{ target.name }}
    {%- endif -%}
{%- endmacro %}
