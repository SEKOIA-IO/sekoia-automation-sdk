from datetime import datetime
from enum import IntEnum, StrEnum

from pydantic import BaseModel, model_validator

from sekoia_automation.asset_connector.models.ocsf.base import OCSFBaseModel
from sekoia_automation.asset_connector.models.ocsf.device import Device


class SBOMTypeId(IntEnum):
    UNKNOWN = 0
    SPDX = 1
    CYCLONEDX = 2
    SWID = 3
    OTHER = 99


class SBOMTypeStr(StrEnum):
    UNKNOWN = "Unknown"
    SPDX = "SPDX"
    CYCLOEDX = "CycloDX"
    SWID = "SWID"
    OTHER = "Other"


class ComponentTypeId(IntEnum):
    UNKNOWN = 0
    FRAMEWORK = 1
    LIBRARY = 2
    OPERATINGSYSTEM = 3
    OTHER = 99


class ComponentTypeStr(StrEnum):
    UNKNOWN = "Unknown"
    FRAMEWORK = "Framework"
    LIBRARY = "Library"
    OPERATINGSYSTEM = "Operating System"
    OTHER = "Other"


class PackageTypeId(IntEnum):
    UNKNOWN = 0
    APPLICATION = 1
    OPERATINGSYSTEM = 2
    OTHER = 99


class PackageTypeStr(StrEnum):
    UNKNOWN = "Unknown"
    APPLICATION = "Application"
    OPERATINGSYSTEM = "Operating System"
    OTHER = "Other"


class Fingerprint(BaseModel):
    algorithm_id: str | None = None
    value: str


class Signature(BaseModel):
    subject: str | None = None
    issuer: str | None = None
    valid: bool | None = None


class SoftwareEnrichmentObject(BaseModel):
    """
    Represents software-related information collected from a device.

    This object describes applications installed on an endpoint and
    enriches the context of a device by providing details such as
    name, version, vendor, installation path, and usage timestamps.
    """

    product_id: str | None = None
    product_name: str | None = None
    version: str | None = None

    vendor_name: str | None = None

    path: str | None = None
    install_time: datetime | None = None
    last_used_time: datetime | None = None

    os: str | None = None

    hashes: list[Fingerprint] | None = None

    is_signed: bool | None = None
    signature: Signature | None = None

    binary_name: str | None = None

    @model_validator(mode="after")
    def validate_signature_consistency(self) -> "SoftwareEnrichmentObject":
        has_signature = self.signature is not None

        if self.is_signed is None:
            self.is_signed = has_signature
            return self

        if self.is_signed and not has_signature:
            raise ValueError("signature is required when is_signed is True")

        if not self.is_signed and has_signature:
            raise ValueError("signature must be None when is_signed is False")

        return self


class SoftwarePackage(BaseModel):
    """
    Represents a distributable software unit (e.g., application, OS package).

    A package corresponds to a deployable or installable artifact, such as an
    application installer, system package, or container image. It identifies
    the main software product being described, including its name, version,
    type, and licensing information.
    """

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
    """
    Represents an individual component within a software package.

    A component is a building block of a software package, such as a library,
    framework, or module.
    Components describe the internal composition of a package.
    """

    version: str
    name: str
    author: str | None = None
    type: ComponentTypeStr | None = None
    type_id: ComponentTypeId | None = None


class SoftwareBillOfMaterials(BaseModel):
    """
    Describes the composition of a software package.

    A Software Bill of Materials (SBOM) provides a structured inventory of all
    components included in a software package, along with associated metadata.
    It is used to track dependencies, assess vulnerabilities, and improve
    transparency in the software supply chain.
    """

    package: SoftwarePackage
    software_components: list[SoftwareComponent] | None = None
    type: SBOMTypeStr | None = None
    type_id: SBOMTypeId | None = None
    uid: str | None = None
    version: str | None = None


class SoftwareOCSFModel(OCSFBaseModel):
    device: Device
    sbom: SoftwareBillOfMaterials | None = None
    enrichments: list[SoftwareEnrichmentObject] | None = None
