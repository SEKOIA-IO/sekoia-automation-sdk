from pydantic import BaseModel

from sekoia_automation.asset_connector.models.ocsf.base import OCSFBaseModel


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


class Group(BaseModel):
    """
    Group model represents a user group.
    https://schema.ocsf.io/1.5.0/objects/group
    """

    name: str
    desc: str | None = None
    privileges: list[str] | None = None
    uid: str | None = None


class User(BaseModel):
    has_mfa: bool
    name: str
    uid: int
    groups: list[Group]
    full_name: str
    email_addr: str


class UserOCSFModel(OCSFBaseModel):
    """
    UserOCSFModel represents a user in the OCSF format.
    https://schema.ocsf.io/1.5.0/classes/user_inventory
    """

    user: User
    enrichments: list[UserEnrichmentObject] | None = None
