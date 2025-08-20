from pydantic import BaseModel

from sekoia_automation.asset_connector.models.ocsf.device import DeviceOCSFModel
from sekoia_automation.asset_connector.models.ocsf.software import SoftwareOCSFModel
from sekoia_automation.asset_connector.models.ocsf.user import UserOCSFModel
from sekoia_automation.asset_connector.models.ocsf.vulnerability import (
    VulnerabilityOCSFModel,
)

AssetItem = VulnerabilityOCSFModel | DeviceOCSFModel | UserOCSFModel | SoftwareOCSFModel


class DefaultAssetConnectorConfiguration(BaseModel):
    """
    Base configuration for asset connectors.
    This configuration is used to define the basic parameters required
    for asset connectors.
    Attributes:
        sekoia_base_url (str | None): The base URL for the Sekoia.io API.
        sekoia_api_key (str): The API key for authentication with the Sekoia.io API.
        frequency (int): The frequency in seconds at which the connector should run.
    """

    sekoia_base_url: str | None
    sekoia_api_key: str
    frequency: int = 60


class AssetList(BaseModel):
    """
    AssetList model for OCSF.
    This model is used to represent a list of assets collected by an asset connector.
    Attributes:
        version (int): The OCSF schema version. ( Sekoia version )
        items (list): A list of asset objects, which can be of various types including
                      VulnerabilityOCSFModel, DeviceOCSFModel,
                      UserOCSFModel, SoftwareOCSFModel, or AssetObject.
    """

    version: int
    items: list[AssetItem] = []
