{% macro generate_schema_name(custom_schema_name, node) -%}
{#
  Maps dbt custom schema config to a ClickHouse database name.

  ClickHouse has databases, not schemas. Project `+schema` values become
  `{custom_schema}_{target.name}` (e.g. gold + dev → gold_dev). Without a
  custom schema, the profile target.schema is used unchanged.

  Args:
      custom_schema_name: Value from model/project `+schema`, or none.
      node: dbt graph node (unused; required by dbt macro signature).

  Returns:
      string: Physical ClickHouse database name for the relation.

  Notes:
      Do not prefix with target.schema (avoids warehouse.gold_dev nesting).
#}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name }}_{{ target.name }}
    {%- endif -%}
{%- endmacro %}
