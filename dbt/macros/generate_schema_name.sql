{% macro generate_schema_name(custom_schema_name, node) -%}
  {{ var('mt_schema_prefix', '') }}{{ custom_schema_name | trim if custom_schema_name else target.schema }}
{%- endmacro %}
