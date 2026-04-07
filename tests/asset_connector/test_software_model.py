import pytest
from pydantic import ValidationError

from sekoia_automation.asset_connector.models.ocsf.base import (
    Metadata,
    Product,
)
from sekoia_automation.asset_connector.models.ocsf.device import (
    Device,
    DeviceTypeId,
    DeviceTypeStr,
)
from sekoia_automation.asset_connector.models.ocsf.software import (
    Signature,
    SoftwareEnrichmentObject,
    SoftwareOCSFModel,
)


def _make_software_ocsf_model(**kwargs) -> SoftwareOCSFModel:
    base_kwargs = {
        "activity_id": 2,
        "activity_name": "Collect",
        "category_name": "Discovery",
        "category_uid": 5,
        "class_name": "Asset",
        "class_uid": 5001,
        "type_name": "Software Inventory Info: Collect",
        "type_uid": 500102,
        "time": 1633036800,
        "metadata": Metadata(product=Product(name="Example"), version="1.0.0"),
        "device": Device(
            type_id=DeviceTypeId.DESKTOP,
            type=DeviceTypeStr.DESKTOP,
            uid="device-1",
            hostname="host-1",
        ),
    }
    base_kwargs.update(kwargs)
    return SoftwareOCSFModel(**base_kwargs)


def test_software_derives_is_signed_to_false_without_signature():
    software = SoftwareEnrichmentObject(name="example")

    assert software.is_signed is False
    assert software.signature is None


def test_software_derives_is_signed_to_true_with_signature_only():
    software = SoftwareEnrichmentObject(
        name="example", signature=Signature(subject="ACME")
    )

    assert software.is_signed is True
    assert software.signature is not None


def test_software_requires_signature_when_is_signed_true():
    with pytest.raises(ValidationError, match="signature is required"):
        SoftwareEnrichmentObject(name="example", is_signed=True)


def test_software_rejects_signature_when_is_signed_false():
    with pytest.raises(ValidationError, match="signature must be None"):
        SoftwareEnrichmentObject(
            name="example",
            is_signed=False,
            signature=Signature(subject="ACME"),
        )


def test_software_accepts_consistent_signed_state():
    software = SoftwareEnrichmentObject(
        name="example",
        is_signed=True,
        signature=Signature(subject="ACME", issuer="CA", valid=True),
    )

    assert software.is_signed is True
    assert software.signature is not None


def test_software_accepts_epoch_time_fields():
    software = SoftwareEnrichmentObject(
        product_name="example",
        install_time=1_712_000_000.0,
        last_used_time=1_712_000_123.0,
    )

    assert software.install_time == 1_712_000_000.0
    assert software.last_used_time == 1_712_000_123.0


def test_software_ocsf_model_allows_missing_software():
    model = _make_software_ocsf_model()

    assert model.software is None


def test_software_ocsf_model_accepts_software_object():
    model = _make_software_ocsf_model(
        software=SoftwareEnrichmentObject(product_name="example", version="1.0.0")
    )

    assert model.software is not None
    assert model.software.product_name == "example"
