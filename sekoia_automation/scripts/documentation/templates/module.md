
{#- -*- mode: jinja2 -*- -#}
{%- macro cell(text) -%}
{{ text | replace('\n','<br/>') | replace('|', '\\|') if gitbook else text | replace('\n','<br/>') }}
{%- endmacro -%}
{%- if gitbook -%}
---
uuid: {{manifest.uuid | tojson}}
name: {{manifest.name | tojson}}
description: {{manifest.description | default('') | tojson}}
---
{%- else -%}
uuid: {{manifest.uuid}}
name: {{manifest.name}}
type: playbook
{%- endif %}

# {{manifest.name}}

{%- if logo_url and gitbook %}

<img src="{{logo_url}}" alt="{{manifest.name}}" width="150" align="right">
{%- elif logo_url %}

![{{manifest.name}}]({{logo_url}}){ align=right width=150 }
{%- endif %}

{{manifest.description}}

## Configuration

{%- if manifest.configuration.properties %}

| Name      |  Type   |  Description  |
| --------- | ------- | --------------------------- |
{% for property in manifest.configuration.properties -%}
| `{{property}}` | `{{manifest.configuration.properties[property]['type']}}` | {{ cell(manifest.configuration.properties[property]['description']) }} |
{% endfor -%}

{%- else %}

This module accepts no configuration.
{% endif -%}

{%- if triggers %}
## Triggers

{%- for trigger in triggers %}

### {{trigger.name}}

{{trigger.description}}

{%- if trigger.arguments.properties %}

**Arguments**

| Name      |  Type   |  Description  |
| --------- | ------- | --------------------------- |
{% for property in trigger.arguments.properties -%}
| `{{property}}` | `{{trigger.arguments.properties[property]['type']}}` | {{ cell(trigger.arguments.properties[property]['description']) }} |
{% endfor %}
{%- endif %}

{%- if trigger.results.properties %}

**Outputs**

| Name      |  Type   |  Description  |
| --------- | ------- | --------------------------- |
{% for property in trigger.results.properties -%}
| `{{property}}` | `{{trigger.results.properties[property]['type']}}` | {{ cell(trigger.results.properties[property]['description']) }} |
{% endfor -%}

{%- endif -%}{# /trigger.arguments.properties #}
{%- endfor -%}{# /triggers #}
{%- endif -%}{# /triggers #}

{%- if actions %}
## Actions
{% for action in actions %}
### {{action.name}}

{{action.description}}

{%- if not gitbook and action.arguments.properties and action.arguments.properties.description %}

**Configuration**

{{action.arguments.properties.description}}

{%- endif -%}

{%- if action.arguments.properties %}

**Arguments**

| Name      |  Type   |  Description  |
| --------- | ------- | --------------------------- |
{% for property in action.arguments.properties -%}
| `{{property}}` | `{{action.arguments.properties[property]['type']}}` | {{ cell(action.arguments.properties[property]['description']) }} |
{% endfor %}
{%- endif -%}

{%- if action.results and action.results.properties %}

**Outputs**

| Name      |  Type   |  Description  |
| --------- | ------- | --------------------------- |
{% for property in action.results.properties -%}
| `{{property}}` | `{{action.results.properties[property]['type']}}` | {{ cell(action.results.properties[property]['description']) }} |
{% endfor %}
{%- endif -%}{# /action.arguments.properties #}
{%- endfor -%}{# /actions #}
{%- endif -%}{# /actions #}

{%- if setup %}
## Set up

{{ setup }}

{%- endif %}

## Extra

Module **`{{manifest.name}}` v{{manifest.version}}**
