{#
  SCD2 effective-date sentinels and run bound for Gold dimensions and bridges.

  Unknown/open windows use fixed UTC DateTime64(3) literals so as-of joins and
  current-row filters stay consistent across ClickHouse models. Change/reappear
  seams use scd2_bound_at() (override in unit tests for deterministic expects).
#}


{% macro scd2_valid_from_unknown() -%}
{#
  Returns the sentinel effective-start timestamp for unknown first versions.

  Returns:
      DateTime64(3, 'UTC'): 1900-01-01 00:00:00.000 — used when
          source_created_at is null on the first SCD2 version of a key.

  Notes:
      Pair with scd2_valid_to_open() for open-ended current rows. Do not use
      for warehouse audit columns (inserted_at / updated_at).
#}
cast('1900-01-01 00:00:00.000' as DateTime64(3, 'UTC'))
{%- endmacro %}


{% macro scd2_valid_to_open() -%}
{#
  Returns the sentinel effective-end timestamp for still-active SCD2 versions.

  Returns:
      DateTime64(3, 'UTC'): 9999-01-01 23:59:59.999 — marks an open validity
          window (is_active = 1). Closed versions replace this with scd2_bound_at().

  Notes:
      Consumers filter current rows with is_active = 1 or valid_to equal to
      this sentinel. Pattern A deletes set valid_to to the expire timestamp.
#}
cast('9999-01-01 23:59:59.999' as DateTime64(3, 'UTC'))
{%- endmacro %}


{% macro scd2_bound_at() -%}
{#
  Returns the single SCD2 seam timestamp for this dbt invocation.

  Returns:
      DateTime64(3, 'UTC') SQL literal from dbt `run_started_at` (ms truncated
      from microseconds). Used for change closes, reappear opens, Pattern A
      delete valid_to, and version SK time basis.

  Notes:
      Emits a compile-time constant so every reference in the model is identical
      (no ClickHouse now64(3) / CTE inlining drift). All Gold SCD2 models in the
      same dbt run share one bound. Override in unit tests to a fixed
      cast(... DateTime64(3, 'UTC')).
#}
cast('{{ run_started_at.strftime("%Y-%m-%d %H:%M:%S") }}.{{ "%03d" | format((run_started_at.microsecond // 1000)) }}' as DateTime64(3, 'UTC'))
{%- endmacro %}
