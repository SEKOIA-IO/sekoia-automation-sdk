from enum import Enum, IntEnum
from typing import Literal

from pydantic import BaseModel

from sekoia_automation.asset_connector.models.ocsf.base import OCSFBaseModel


class GeoLocation(BaseModel):
    """
    GeoLocation model represents the geographical location of a device.
    https://schema.ocsf.io/1.5.0/objects/location
    """

    city: str | None = None
    country: str | None = None


class OSTypeId(IntEnum):
    UNKNOWN = 0
    OTHER = 99
    WINDOWS = 100
    WINDOWS_MOBILE = 101
    LINUX = 200
    ANDROID = 201
    MACOS = 300
    IOS = 301
    IPADOS = 302
    SOLARIS = 400
    AIX = 401
    HPUX = 402


class OSTypeStr(Enum):
    UNKNOWN = "unknown"
    OTHER = "other"
    WINDOWS = "windows"
    WINDOWS_MOBILE = "windows mobile"
    LINUX = "linux"
    ANDROID = "android"
    MACOS = "macos"
    IOS = "ios"
    IPADOS = "ipados"
    SOLARIS = "solaris"
    AIX = "aix"
    HPUX = "hp-ux"


class OperatingSystem(BaseModel):
    """
    OperatingSystem model represents the operating system of a device.
    https://schema.ocsf.io/1.5.0/objects/os
    """

    name: str | None = None
    type: OSTypeStr | None = None
    type_id: OSTypeId | None = None


class DeviceTypeId(IntEnum):
    UNKNOWN = 0
    SERVER = 1
    DESKTOP = 2
    LAPTOP = 3
    TABLET = 4
    MOBILE = 5
    VIRTUAL = 6
    IOT = 7
    BROWSER = 8
    FIREWALL = 9
    SWITCH = 10
    HUB = 11
    ROUTER = 12
    IDS = 13
    IPS = 14
    LOAD_BALANCER = 15
    OTHER = 99


class DeviceTypeStr(Enum):
    UNKNOWN = "Unknown"
    SERVER = "Server"
    DESKTOP = "Desktop"
    LAPTOP = "Laptop"
    TABLET = "Tablet"
    MOBILE = "Mobile"
    VIRTUAL = "Virtual"
    IOT = "IOT"
    BROWSER = "Browser"
    FIREWALL = "Firewall"
    SWITCH = "Switch"
    HUB = "Hub"
    ROUTER = "Router"
    IDS = "IDS"
    IPS = "IPS"
    LOAD_BALANCER = "Load Balancer"
    OTHER = "Other"


class Device(BaseModel):
    """
    Device model represents a device object in the OCSF format.
    https://schema.ocsf.io/1.5.0/objects/device
    """

    type_id: DeviceTypeId
    type: DeviceTypeStr
    uid: str
    location: GeoLocation | None = None
    os: OperatingSystem | None = None
    hostname: str


class EncryptionObject(BaseModel):
    partitions: dict[str, Literal["Disabled", "Enabled"]]


class DeviceDataObject(BaseModel):
    """
    DataObject represents some data related to a device.
    ( Firewall and Storage encryption )
    """

    Firewall_status: Literal["Disabled", "Enabled"] | None = None
    Storage_encryption: EncryptionObject | None = None
    Users: list[str] | None = None


class DeviceEnrichmentObject(BaseModel):
    """
    Enrichment Object represents additional information about a device.
    """

    name: str
    value: str
    data: DeviceDataObject


class DeviceOCSFModel(OCSFBaseModel):
    """
    DeviceOCSFModel represents a device in the OCSF format.
    https://schema.ocsf.io/1.5.0/classes/inventory_info
    """

    device: Device
    enrichments: list[DeviceEnrichmentObject] | None = None
