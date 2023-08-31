"""Aws base client wrapper with its config class."""

from functools import cached_property
from typing import Generic, TypeVar

from aiobotocore.session import AioCredentials, AioSession, ClientCreatorContext
from botocore.credentials import CredentialProvider
from pydantic import BaseModel, Field


class AwsConfiguration(BaseModel):
    """AWS client base configuration."""

    aws_access_key_id: str = Field(description="AWS access key id")
    aws_secret_access_key: str = Field(description="AWS secret access key")
    aws_region: str = Field(description="AWS region name")


AwsConfigurationT = TypeVar("AwsConfigurationT", bound=AwsConfiguration)


class _CredentialsProvider(CredentialProvider):
    """Custom credentials provider."""

    METHOD = "_sekoia_credentials_provider"

    def __init__(self, access_key: str, secret_key: str) -> None:
        """
        Initialize CredentialsProvider.

        Args:
            access_key: str
            secret_key: str
        """
        self.access_key = access_key
        self.secret_key = secret_key

    async def load(self) -> AioCredentials:
        """
        Load credentials.

        Returns:
            ReadOnlyCredentials
        """
        return AioCredentials(
            access_key=self.access_key,
            secret_key=self.secret_key,
            method=self.METHOD,
        )


class AwsClient(Generic[AwsConfigurationT]):
    """
    Aws base client.

    All other clients should extend this base client.
    """

    _configuration: AwsConfigurationT | None = None
    _credentials_provider: _CredentialsProvider | None = None

    def __init__(self, configuration: AwsConfigurationT | None = None) -> None:
        """
        Initialize AwsClient.

        Args:
            configuration: AwsConfigurationT
        """
        self._configuration = configuration

        if self._configuration:
            self._credentials_provider = _CredentialsProvider(
                self._configuration.aws_access_key_id,
                self._configuration.aws_secret_access_key,
            )

    @cached_property
    def get_session(self) -> AioSession:
        """
        Get AWS session.

        Returns:
            AioSession:
        """
        session = AioSession()

        # Make our own creds provider to be executed at 1 place
        if self._credentials_provider:
            credential_provider = session.get_component("credential_provider")
            credential_provider.insert_before("env", self._credentials_provider)

        return session

    def get_client(
        self,
        client_name: str,
        region_name: str | None = None,
    ) -> ClientCreatorContext:
        """
        Get AWS client.

        Args:
            client_name: str
            region_name: str | None

        Returns:
            ClientCreatorContext:
        """
        _region_name = region_name
        if not region_name and self._configuration is not None:
            _region_name = self._configuration.aws_region

        if not _region_name:
            raise ValueError("Region name is required. You should specify it.")

        return self.get_session.create_client(
            client_name,
            region_name=_region_name,
        )
