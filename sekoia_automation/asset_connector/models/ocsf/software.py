from enum import IntEnum, StrEnum

from pydantic import BaseModel, model_validator

from sekoia_automation.asset_connector.models.ocsf.base import OCSFBaseModel
from sekoia_automation.asset_connector.models.ocsf.device import Device, OperatingSystem


class SBOMTypeId(IntEnum):
    UNKNOWN = 0
    SPDX = 1
    CYCLONEDX = 2
    SWID = 3
    OTHER = 99


class SBOMTypeStr(StrEnum):
    UNKNOWN = "Unknown"
    SPDX = "SPDX"
    CYCLONEDX = "CycloneDX"
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


class SignatureAlgorithmId(IntEnum):
    UNKNOWN = 0
    DSA = 1
    RSA = 2
    ECDSA = 3
    AUTHENTICODE = 4
    OTHER = 99


class SignatureAlgorithmStr(StrEnum):
    UNKNOWN = "Unknown"
    DSA = "DSA"
    RSA = "RSA"
    ECDSA = "ECDSA"
    AUTHENTICODE = "Authenticode"
    OTHER = "Other"


class SignatureStateId(IntEnum):
    UNKNOWN = 0
    VALID = 1
    EXPIRED = 2
    REVOKED = 3
    SUSPENDED = 4
    PENDING = 5
    UNTRUSTED = 6
    DISTRUSTED = 7
    WRONG_USAGE = 8
    BAD = 9
    BROKEN = 10
    OTHER = 99


class SignatureStateStr(StrEnum):
    UNKNOWN = "Unknown"
    VALID = "Valid"
    EXPIRED = "Expired"
    REVOKED = "Revoked"
    SUSPENDED = "Suspended"
    PENDING = "Pending"
    UNTRUSTED = "Untrusted"
    DISTRUSTED = "Distrusted"
    WRONG_USAGE = "WrongUsage"
    BAD = "Bad"
    BROKEN = "Broken"
    OTHER = "Other"


class FingerprintAlgorithmId(IntEnum):
    UNKNOWN = 0
    MD5 = 1
    SHA1 = 2
    SHA256 = 3
    SHA512 = 4
    CTPH = 5
    TLSH = 6
    QUICKXORHASH = 7
    SHA224 = 8
    SHA384 = 9
    SHA512_224 = 10
    SHA512_256 = 11
    SHA3_224 = 12
    SHA3_256 = 13
    SHA3_384 = 14
    SHA3_512 = 15
    XXHASH64 = 16
    XXHASH128 = 17
    IMPHASH = 18
    NPF = 19
    HASSH = 20
    OTHER = 99


class FingerprintAlgorithmStr(StrEnum):
    UNKNOWN = "Unknown"
    MD5 = "MD5"
    SHA1 = "SHA-1"
    SHA256 = "SHA-256"
    SHA512 = "SHA-512"
    CTPH = "CTPH"
    TLSH = "TLSH"
    QUICKXORHASH = "quickXorHash"
    SHA224 = "SHA-224"
    SHA384 = "SHA-384"
    SHA512_224 = "SHA-512/224"
    SHA512_256 = "SHA-512/256"
    SHA3_224 = "SHA3-224"
    SHA3_256 = "SHA3-256"
    SHA3_384 = "SHA3-384"
    SHA3_512 = "SHA3-512"
    XXHASH64 = "xxHash H3 64-bit"
    XXHASH128 = "xxHash H3 128-bit"
    IMPHASH = "Imphash"
    NPF = "NPF"
    HASSH = "HASSH"
    OTHER = "Other"


# https://schema.ocsf.io/1.8.0/objects/fingerprint
class Fingerprint(BaseModel):
    algorithm: FingerprintAlgorithmStr | None = None
    algorithm_id: FingerprintAlgorithmId | None = None

    value: str

    @model_validator(mode="after")
    def sync_algorithm(self) -> "Fingerprint":
        if self.algorithm_id is not None and self.algorithm is None:
            self.algorithm = FingerprintAlgorithmStr[self.algorithm_id.name]

        if self.algorithm is not None and self.algorithm_id is None:
            self.algorithm_id = FingerprintAlgorithmId[self.algorithm.name]

        return self


# https://schema.ocsf.io/1.8.0/objects/certificate
class DigitalCertificate(BaseModel):
    created_time: float | None = None
    expiration_time: float | None = None

    fingerprints: list[Fingerprint] | None = None

    is_self_signed: bool | None = None

    issuer: str
    subject: str | None = None

    serial_number: str

    sans: list[str] | None = None

    uid: str | None = None
    version: str | None = None


# https://schema.ocsf.io/1.8.0/objects/digital_signature
class DigitalSignature(BaseModel):
    """
    Represents a digital signature used to verify the authenticity
    and integrity of a software.
    """

    algorithm: SignatureAlgorithmStr | None = None
    algorithm_id: SignatureAlgorithmId | None = None

    certificate: DigitalCertificate | None = None

    state: SignatureStateStr | None = None
    state_id: SignatureStateId | None = None

    created_time: float | None = None

    digest: Fingerprint | None = None

    @model_validator(mode="after")
    def sync_enums(self) -> "DigitalSignature":
        if self.algorithm_id is not None and self.algorithm is None:
            self.algorithm = SignatureAlgorithmStr[self.algorithm_id.name]

        if self.algorithm is not None and self.algorithm_id is None:
            self.algorithm_id = SignatureAlgorithmId[self.algorithm.name]

        if self.state_id is not None and self.state is None:
            self.state = SignatureStateStr[self.state_id.name]

        if self.state is not None and self.state_id is None:
            self.state_id = SignatureStateId[self.state.name]

        return self


class SoftwareEnrichmentObject(BaseModel):
    """
    Represents software-related information collected from a device.

    This object describes applications installed on an endpoint and
    enriches the context of a device by providing details such as
    name, version, vendor, installation path, and usage timestamps.
    """

    uid: str | None = None
    name: str | None = None
    version: str | None = None

    vendor_name: str | None = None

    path: str | None = None
    install_time: float | None = None
    last_used_time: float | None = None

    os: OperatingSystem | None = None

    hashes: list[Fingerprint] | None = None

    signature: DigitalSignature | None = None

    binary_name: str | None = None
    architecture: str | None = None
    last_user_name: str | None = None


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

    @model_validator(mode="after")
    def sync_type(self) -> "SoftwareBillOfMaterials":
        if self.type_id and not self.type:
            self.type = SBOMTypeStr[self.type_id.name]

        if self.type and not self.type_id:
            self.type_id = SBOMTypeId[self.type.name]

        return self


class SoftwareOCSFModel(OCSFBaseModel):
    device: Device
    software: SoftwareEnrichmentObject | None = None
    # sbom corresponds to the software described in `software`
    sbom: SoftwareBillOfMaterials | None = None
