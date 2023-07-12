"""Tests related to sekoia_automation.helpers.aio.aws module."""

import pytest
from aiobotocore.session import AioSession

from sekoia_automation.helpers.aio.aws.client import AwsClient, AwsConfiguration


@pytest.fixture
def aws_configuration():
    """
    Fixture for AwsConfiguration.

    Returns:
        AwsConfiguration:
    """
    return AwsConfiguration(
        aws_access_key_id="ACCESS_KEY",
        aws_secret_access_key="SECRET_KEY",
        aws_region="us-east-1",
    )


@pytest.mark.asyncio
async def test_aws_client_init(aws_configuration):
    """
    Test AwsClient initialization.

    Args:
        aws_configuration: AwsConfiguration
    """
    client = AwsClient(aws_configuration)

    assert client._configuration == aws_configuration


@pytest.mark.asyncio
async def test_aws_client_get_session(aws_configuration):
    """
    Test AwsClient get_session.

    Args:
        aws_configuration: AwsConfiguration
    """
    client = AwsClient(aws_configuration)

    session = client.get_session

    assert isinstance(session, AioSession)

    assert (
        session.get_component("credential_provider").get_provider(
            "_sekoia_credentials_provider"
        )
        == client._credentials_provider
    )

    assert (
        session.get_component("credential_provider")._get_provider_offset(
            "_sekoia_credentials_provider"
        )
        == 0
    )
