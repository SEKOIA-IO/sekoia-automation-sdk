from pydantic import Field

from sekoia_automation import SekoiaAutomationBaseModel
from sekoia_automation.action import Action
from sekoia_automation.connector import Connector
from sekoia_automation.module import Module
from sekoia_automation.trigger import Trigger


class ModuleConfiguration(SekoiaAutomationBaseModel):
    module_field: str
    api_key: str = Field(json_schema_extra={"secret": True})
    password: str = Field(json_schema_extra={"secret": True})


class SampleModule(Module):
    configuration: ModuleConfiguration


class TriggerConfiguration(SekoiaAutomationBaseModel):
    trigger_field: int = 0


class Results(SekoiaAutomationBaseModel):
    results_field: str


class SampleTrigger(Trigger):
    module: SampleModule
    configuration: TriggerConfiguration
    name = "Sample Trigger"
    description = "My Sample Trigger Description"
    results_model = Results

    def run(self):
        raise NotImplementedError


class SampleArguments(SekoiaAutomationBaseModel):
    argument: bool


class SampleAction(Action):
    module: SampleModule

    name = "Sample Action"
    description = "My Sample Action Description"
    results_model = Results

    def run(self, arguments: SampleArguments):
        raise NotImplementedError


class SampleConnector(Connector):
    module: SampleModule
    name = "Sample Connector"
    description = "My Sample Connector Description"

    def run(self):
        raise NotImplementedError
