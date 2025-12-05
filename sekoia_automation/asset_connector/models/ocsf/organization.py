from pydantic import BaseModel


class Organization(BaseModel):
    """
    Organization model represents an organization.
    https://schema.ocsf.io/1.6.0/objects/organization
    """

    name: str
    ou_name: str | None = None
    ou_uid: str | None = None
    uid: str | None = None
