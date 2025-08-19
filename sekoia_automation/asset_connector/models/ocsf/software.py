from sekoia_automation.asset_connector.models.ocsf.base import OCSFBaseModel
from sekoia_automation.asset_connector.models.ocsf.device import Device


class SoftwarePackage:
    name: str
    version: str
    uid: str | None = None
    cpe_name: str | None = None
    license: str | None = None
    license_url: str | None = None
    release: str | None = None
    type: str | None = None
    type_id: int | None = None


class SoftwareComponent:
    version: str
    name: str
    author: str | None = None
    type: str | None = None
    type_id: int | None = None


class SoftwareBillOfMaterials:
    package: SoftwarePackage
    software_components: list[SoftwareComponent] | None = None
    type: str | None = None
    type_id: int | None = None
    uid: str | None = None
    version: str | None = None


class SoftwareOCSFModel(OCSFBaseModel):
    device: Device
    sbom: SoftwareBillOfMaterials | None = None
