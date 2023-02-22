from sekoia_automation.module import Module
from {{cookiecutter.module_name.lower().replace(" ", "_")}}_modules.models import {{cookiecutter.module_name.title().replace(" ", "")}}ModuleConfiguration


class {{cookiecutter.module_name.title().replace(" ", "")}}Module(Module):
    configuration: {{cookiecutter.module_name.title().replace(" ", "")}}ModuleConfiguration
