import importlib

import pytest


@pytest.mark.parametrize(
    "module_name, symbol",
    [
        ("base", "OCSFBaseModel"),
        ("device", "DeviceOCSFModel"),
        ("group", "Group"),
        ("organization", "Organization"),
        ("risk_level", "RiskLevelId"),
        ("software", "SoftwareOCSFModel"),
        ("user", "UserOCSFModel"),
        ("vulnerability", "VulnerabilityOCSFModel"),
    ],
)
def test_ocsf_models_are_reexported_from_standalone_package(module_name, symbol):
    module = importlib.import_module(
        f"sekoia_automation.asset_connector.models.ocsf.{module_name}"
    )

    obj = getattr(module, symbol)

    assert obj.__module__ == f"sekoia_automation_models.ocsf.{module_name}"
