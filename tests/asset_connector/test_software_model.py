import pytest
from pydantic import ValidationError

from sekoia_automation.asset_connector.models.ocsf.software import (
    Signature,
    Software,
)


def test_software_derives_is_signed_to_false_without_signature():
    software = Software(name="example")

    assert software.is_signed is False
    assert software.signature is None


def test_software_derives_is_signed_to_true_with_signature_only():
    software = Software(name="example", signature=Signature(subject="ACME"))

    assert software.is_signed is True
    assert software.signature is not None


def test_software_requires_signature_when_is_signed_true():
    with pytest.raises(ValidationError, match="signature is required"):
        Software(name="example", is_signed=True)


def test_software_rejects_signature_when_is_signed_false():
    with pytest.raises(ValidationError, match="signature must be None"):
        Software(
            name="example",
            is_signed=False,
            signature=Signature(subject="ACME"),
        )


def test_software_accepts_consistent_signed_state():
    software = Software(
        name="example",
        is_signed=True,
        signature=Signature(subject="ACME", issuer="CA", valid=True),
    )

    assert software.is_signed is True
    assert software.signature is not None
