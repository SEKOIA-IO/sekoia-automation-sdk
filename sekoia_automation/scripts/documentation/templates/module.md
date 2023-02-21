{#- -*- mode: jinja2 -*- -#}
# {{manifest.name}}

{%- if logo_filename %}

![{{manifest.name}}](/assets/playbooks/library/{{logo_filename}}){ align=right width=150 }
{%- endif %}

{{manifest.description}}

## Configuration

{%- if manifest.configuration.properties %}

| Name      |  Type   |  Description  |
| --------- | ------- | --------------------------- |
{% for property in manifest.configuration.properties -%}
| `{{property}}` | `{{manifest.configuration.properties[property]['type']}}` | {{manifest.configuration.properties[property]['description'] | replace('\n','<br/>')}} |
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
| `{{property}}` | `{{trigger.arguments.properties[property]['type']}}` | {{trigger.arguments.properties[property]['description'] | replace('\n','<br/>')}} |
{% endfor %}
{%- endif %}

{%- if trigger.results.properties %}

**Outputs**

| Name      |  Type   |  Description  |
| --------- | ------- | --------------------------- |
{% for property in trigger.results.properties -%}
| `{{property}}` | `{{trigger.results.properties[property]['type']}}` | {{trigger.results.properties[property]['description'] | replace('\n','<br/>')}} |
{% endfor -%}

{%- endif -%}{# /trigger.arguments.properties #}
{%- endfor -%}{# /triggers #}
{%- endif -%}{# /triggers #}

{%- if actions %}
## Actions
{% for action in actions %}
### {{action.name}}

{{action.description}}

{%- if action.arguments.properties %}

**Arguments**

| Name      |  Type   |  Description  |
| --------- | ------- | --------------------------- |
{% for property in action.arguments.properties -%}
| `{{property}}` | `{{action.arguments.properties[property]['type']}}` | {{action.arguments.properties[property]['description'] | replace('\n','<br/>')}} |
{% endfor %}
{%- endif -%}

{%- if action.results and action.results.properties %}

**Outputs**

| Name      |  Type   |  Description  |
| --------- | ------- | --------------------------- |
{% for property in action.results.properties -%}
| `{{property}}` | `{{action.results.properties[property]['type']}}` | {{action.results.properties[property]['description'] | replace('\n','<br/>')}} |
{% endfor %}
{%- endif -%}{# /action.arguments.properties #}
{%- endfor -%}{# /actions #}
{%- endif -%}{# /actions #}

## Extra

Module **`{{manifest.name}}` v{{manifest.version}}**
