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
    DigitalSignature,
    Fingerprint,
    FingerprintAlgorithmId,
    FingerprintAlgorithmStr,
    SBOMTypeId,
    SBOMTypeStr,
    SignatureAlgorithmId,
    SignatureAlgorithmStr,
    SignatureStateId,
    SignatureStateStr,
    SoftwareBillOfMaterials,
    SoftwareEnrichmentObject,
    SoftwareOCSFModel,
    SoftwarePackage,
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


def test_software_accepts_signature_object():
    software = SoftwareEnrichmentObject(
        name="example",
        signature=DigitalSignature(
            algorithm=SignatureAlgorithmStr.RSA,
            state=SignatureStateStr.VALID,
        ),
    )

    assert software.signature is not None
    assert software.signature.algorithm == SignatureAlgorithmStr.RSA
    assert software.signature.state == SignatureStateStr.VALID


def test_software_accepts_epoch_time_fields():
    software = SoftwareEnrichmentObject(
        name="example",
        install_time=1_712_000_000.0,
        last_used_time=1_712_000_123.0,
    )

    assert software.install_time == 1_712_000_000.0
    assert software.last_used_time == 1_712_000_123.0


def test_digital_signature_syncs_enum_from_ids():
    signature = DigitalSignature(
        algorithm_id=SignatureAlgorithmId.RSA,
        state_id=SignatureStateId.VALID,
    )

    assert signature.algorithm == SignatureAlgorithmStr.RSA
    assert signature.state == SignatureStateStr.VALID


def test_digital_signature_syncs_ids_from_enum_values():
    signature = DigitalSignature(
        algorithm=SignatureAlgorithmStr.ECDSA,
        state=SignatureStateStr.EXPIRED,
    )

    assert signature.algorithm_id == SignatureAlgorithmId.ECDSA
    assert signature.state_id == SignatureStateId.EXPIRED


def test_fingerprint_syncs_enum_from_id():
    fingerprint = Fingerprint(
        algorithm_id=FingerprintAlgorithmId.SHA256,
        value="abc",
    )

    assert fingerprint.algorithm == FingerprintAlgorithmStr.SHA256


def test_fingerprint_syncs_id_from_enum():
    fingerprint = Fingerprint(
        algorithm=FingerprintAlgorithmStr.SHA512,
        value="abc",
    )

    assert fingerprint.algorithm_id == FingerprintAlgorithmId.SHA512


def test_sbom_syncs_type_from_type_id():
    sbom = SoftwareBillOfMaterials(
        package=SoftwarePackage(name="pkg", version="1.0.0"),
        type_id=SBOMTypeId.SPDX,
    )

    assert sbom.type == SBOMTypeStr.SPDX


def test_sbom_syncs_type_id_from_type():
    sbom = SoftwareBillOfMaterials(
        package=SoftwarePackage(name="pkg", version="1.0.0"),
        type=SBOMTypeStr.CYCLONEDX,
    )

    assert sbom.type_id == SBOMTypeId.CYCLONEDX


def test_software_ocsf_model_allows_missing_software():
    model = _make_software_ocsf_model()

    assert model.software is None


def test_software_ocsf_model_accepts_software_object():
    model = _make_software_ocsf_model(
        software=SoftwareEnrichmentObject(name="example", version="1.0.0")
    )

    assert model.software is not None
    assert model.software.name == "example"


def test_software_accepts_architecture():
    software = SoftwareEnrichmentObject(name="example", architecture="x86_64")

    assert software.architecture == "x86_64"


def test_software_accepts_last_user_name():
    software = SoftwareEnrichmentObject(name="example", last_user_name="jdoe")

    assert software.last_user_name == "jdoe"


def test_software_architecture_and_last_user_name_are_optional():
    software = SoftwareEnrichmentObject(name="example")

    assert software.architecture is None
    assert software.last_user_name is None
