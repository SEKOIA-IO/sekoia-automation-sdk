from enum import IntEnum, StrEnum
from typing import Literal

from pydantic import BaseModel

from sekoia_automation.asset_connector.models.ocsf.base import OCSFBaseModel
from sekoia_automation.asset_connector.models.ocsf.group import Group
from sekoia_automation.asset_connector.models.ocsf.organization import Organization
from sekoia_automation.asset_connector.models.ocsf.risk_level import (
    RiskLevelId,
    RiskLevelStr,
)


class NetworkInterfaceTypeId(IntEnum):
    UNKNOWN = 0
    WIRED = 1
    WIRELESS = 2
    MOBILE = 3
    TUNNEL = 4
    OTHER = 99


class NetworkInterfaceTypeStr(StrEnum):
    UNKNOWN = "Unknown"
    WIRED = "Wired"
    WIRELESS = "Wireless"
    MOBILE = "Mobile"
    TUNNEL = "Tunnel"
    OTHER = "Other"


class NetworkInterface(BaseModel):
    """
    NetworkInterface model represents a network interface of a device.
    https://schema.ocsf.io/1.5.0/objects/network_interface
    """

    hostname: str | None = None
    ip: str | None = None
    mac: str | None = None
    name: str | None = None
    type: NetworkInterfaceTypeStr | None = None
    type_id: NetworkInterfaceTypeId | None = None
    uid: str | None = None


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


class OSTypeStr(StrEnum):
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


class DeviceTypeStr(StrEnum):
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
    autoscale_uid: str | None = None
    boot_time: str | None = None
    boot_uid: str | None = None
    created_time: float | None = None
    desc: str | None = None
    domain: str | None = None
    eid: str | None = None
    first_seen_time: float | None = None
    groups: list[Group] | None = None
    hypervisor: str | None = None
    iccid: str | None = None
    imei_list: list[str] | None = None
    ip: str | None = None
    is_backed_up: bool | None = None
    is_compliant: bool | None = None
    is_managed: bool | None = None
    is_mobile_account_active: bool | None = None
    is_personal: bool | None = None
    is_shared: bool | None = None
    is_supervised: bool | None = None
    is_trusted: bool | None = None
    last_seen_time: float | None = None
    meid: str | None = None
    model: str | None = None
    name: str | None = None
    network_interfaces: list[NetworkInterface] | None = None
    org: Organization | None = None
    os_machine_uuid: str | None = None
    region: str | None = None
    risk_level: RiskLevelStr | None = None
    risk_level_id: RiskLevelId | None = None
    risk_score: int | None = None
    subnet: str | None = None
    udid: str | None = None
    uid_alt: str | None = None
    vendor_name: str | None = None


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
