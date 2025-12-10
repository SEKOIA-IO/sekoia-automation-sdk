from enum import IntEnum, StrEnum

from pydantic import BaseModel

from sekoia_automation.asset_connector.models.ocsf.base import OCSFBaseModel
from sekoia_automation.asset_connector.models.ocsf.group import Group
from sekoia_automation.asset_connector.models.ocsf.organization import Organization
from sekoia_automation.asset_connector.models.ocsf.risk_level import (
    RiskLevelId,
    RiskLevelStr,
)


class UserDataObject(BaseModel):
    """
    DataObject represents some data related to a user.
    logon information, activation, ...
    """

    is_enabled: bool | None = None
    last_logon: str | None = None
    bad_password_count: int | None = None
    number_of_logons: int | None = None


class UserEnrichmentObject(BaseModel):
    """
    Enrichment Object represents additional information about a user.
    """

    name: str
    value: str
    data: UserDataObject


class AccountTypeId(IntEnum):
    UNKNOWN = 0
    LDAP_ACCOUNT = 1
    WINDOWS_ACCOUNT = 2
    GCP_ACCOUNT = 5
    AZURE_AD_ACCOUNT = 6
    MAC_OS_ACCOUNT = 7
    APPLE_ACCOUNT = 8
    LINUX_ACCOUNT = 9
    AWS_ACCOUNT = 10
    GCP_PROJECT = 11
    OCI_COMPARTMENT = 12
    AZURE_SUBSCRIPTION = 13
    SALESFORCE_ACCOUNT = 14
    GOOGLE_WORKSPACE = 15
    SERVICENOW_INSTANCE = 16
    M365_TENANT = 17
    EMAIL_ACCOUNT = 18
    OTHER = 99


class AccountTypeStr(StrEnum):
    UNKNOWN = "Unknown"
    LDAP_ACCOUNT = "LDAP Account"
    WINDOWS_ACCOUNT = "Windows Account"
    GCP_ACCOUNT = "GCP Account"
    AZURE_AD_ACCOUNT = "Azure AD Account"
    MAC_OS_ACCOUNT = "Mac OS Account"
    APPLE_ACCOUNT = "Apple Account"
    LINUX_ACCOUNT = "Linux Account"
    AWS_ACCOUNT = "AWS Account"
    GCP_PROJECT = "GCP Project"
    OCI_COMPARTMENT = "OCI Compartment"
    AZURE_SUBSCRIPTION = "Azure Subscription"
    SALESFORCE_ACCOUNT = "Salesforce Account"
    GOOGLE_WORKSPACE = "Google Workspace"
    SERVICENOW_INSTANCE = "ServiceNow Instance"
    M365_TENANT = "M365 Tenant"
    EMAIL_ACCOUNT = "Email Account"
    OTHER = "Other"


class UserTypeId(IntEnum):
    UNKNOWN = 0
    USER = 1
    ADMIN = 2
    SYSTEM = 3
    SERVICE = 4
    OTHER = 99


class UserTypeStr(StrEnum):
    UNKNOWN = "Unknown"
    USER = "User"
    ADMIN = "Admin"
    SYSTEM = "System"
    SERVICE = "Service"
    OTHER = "Other"


class Account(BaseModel):
    """
    Account model represents a user account.
    https://schema.ocsf.io/1.5.0/objects/account
    """

    name: str
    type_id: AccountTypeId
    type: AccountTypeStr
    uid: str | None = None


class User(BaseModel):
    has_mfa: bool | None = None
    name: str
    uid: str
    account: Account | None = None
    groups: list[Group] | None = None
    full_name: str | None = None
    email_addr: str | None = None
    display_name: str | None = None
    domain: str | None = None
    forward_addr: str | None = None
    risk_level: RiskLevelStr | None = None
    risk_level_id: RiskLevelId | None = None
    risk_score: int | None = None
    type_id: UserTypeId | None = None
    type: UserTypeStr | None = None
    uid_alt: str | None = None
    org: Organization | None = None


class UserOCSFModel(OCSFBaseModel):
    """
    UserOCSFModel represents a user in the OCSF format.
    https://schema.ocsf.io/1.5.0/classes/user_inventory
    """

    user: User
    enrichments: list[UserEnrichmentObject] | None = None
