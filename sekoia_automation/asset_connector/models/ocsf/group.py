from pydantic import BaseModel


class Group(BaseModel):
    """
    Group model represents a user group.
    https://schema.ocsf.io/1.5.0/objects/group
    """

    name: str
    desc: str | None = None
    privileges: list[str] | None = None
    uid: str | None = None
