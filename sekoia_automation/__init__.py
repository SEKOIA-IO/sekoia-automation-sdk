from pydantic import BaseModel, ConfigDict


class SekoiaAutomationBaseModel(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
