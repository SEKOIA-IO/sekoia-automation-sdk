from enum import IntEnum, Enum

from pydantic import BaseModel

from sekoia_automation.asset_connector.models.ocsf.base import OCSFBaseModel
from sekoia_automation.asset_connector.models.ocsf.device import Device


class SBOMTypeId(IntEnum):
    UNKNOWN = 0
    SPDX = 1
    CYCLOEDX = 2
    SWID = 3
    OTHER = 99


class SBOMTypeStr(Enum):
    UNKNOWN = "Unknown"
    SPDX = "SPDX"
    CYCLOEDX = "CycloDX"
    SWID = "SWID"
    OTHER = "Other"


class ComponentTypeId(IntEnum):
    UNKNOWN = 0
    FRAMEWORK = 1
    LIBRARY= 2
    OPERATINGSYSTEM= 3
    OTHER = 99


class ComponentTypeStr(Enum):
    UNKNOWN = "Unknown"
    FRAMEWORK = "Framework"
    LIBRARY = "Library"
    OPERATINGSYSTEM = "Operating System"
    OTHER = "Other"


class PackageTypeId(IntEnum):
    UNKNOWN = 0
    APPLICATION = 1
    OPERATINGSYSTEM= 2
    OTHER = 99


class PackageTypeStr(Enum):
    UNKNOWN = "Unknown"
    APPLICATION = "Application"
    OPERATINGSYSTEM = "Operating System"
    OTHER = "Other"


class SoftwarePackage(BaseModel):
    name: str
    version: str
    uid: str | None = None
    cpe_name: str | None = None
    license: str | None = None
    license_url: str | None = None
    release: str | None = None
    type: PackageTypeStr | None = None
    type_id: PackageTypeId | None = None


class SoftwareComponent(BaseModel):
    version: str
    name: str
    author: str | None = None
    type: ComponentTypeStr | None = None
    type_id: ComponentTypeId | None = None


class SoftwareBillOfMaterials(BaseModel):
    package: SoftwarePackage
    software_components: list[SoftwareComponent] | None = None
    type: SBOMTypeStr | None = None
    type_id: SBOMTypeId | None = None
    uid: str | None = None
    version: str | None = None


class SoftwareOCSFModel(OCSFBaseModel):
    device: Device
    sbom: SoftwareBillOfMaterials | None = None
