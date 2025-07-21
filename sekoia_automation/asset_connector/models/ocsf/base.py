from typing import Literal

from pydantic import BaseModel


class Product(BaseModel):
    """
    Product model for OCSF.
    https://schema.ocsf.io/1.5.0/objects/product
    attributes:
        name (str): The name of the product.
        vendor_name (str | None): The name of the vendor. Defaults to None.
        version (str | None): The version of the product.
    """

    name: str
    vendor_name: str | None = None
    version: str | None = None


class Metadata(BaseModel):
    """
    Metadata model for OCSF.
    """

    product: Product
    version: str


class OCSFBaseModel(BaseModel):
    """
    Base model for OCSF activities.
    This model includes common fields that are used in OCSF activities.
    """

    activity_id: int
    activity_name: str
    category_name: str
    category_uid: int
    class_name: str
    class_uid: int
    type_name: str
    type_uid: int
    severity: (
        Literal[
            "Unknown",
            "Informational",
            "Low",
            "Medium",
            "High",
            "Critical",
            "Fatal",
            "Other",
        ]
        | None
    ) = None
    severity_id: int | None = None
    time: float
    metadata: Metadata
