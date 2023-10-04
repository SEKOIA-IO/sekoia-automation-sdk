# natives
import io
import json
import os
import uuid
from pathlib import Path, PosixPath, WindowsPath
from unittest import mock

import boto3
import pytest
from botocore.config import Config

# thrid parties
from s3path import S3Path

# internal
from sekoia_automation.storage import (
    PersistentJSON,
    _get_tls_client_credentials,
    get_data_path,
    get_s3_data_path,
    temp_directory,
    write,
)


def test_persistentjson(storage):
    # The first time, object should be an empty dict
    with PersistentJSON("test.json", data_path=storage) as cache:
        assert cache == {}
        cache["key"] = "value"

    # The second time, the object is retrieved
    with PersistentJSON("test.json", data_path=storage) as cache2:
        assert cache2 == {"key": "value"}

    # Make sure the file exists and has the correct content
    filepath = storage / "test.json"
    assert filepath.is_file()

    with filepath.open("r") as f:
        assert json.load(f) == {"key": "value"}


def test_temp_directory(storage):
    directory = temp_directory(storage)
    assert (storage / directory).is_dir()


def test_write_basic(storage):
    filepath = write("test.txt", "content", temp_dir=False, data_path=storage)

    with (storage / filepath).open("r") as f:
        assert f.read() == "content"


def test_write_temp(storage):
    filepath = write("test.txt", "content", data_path=storage)
    dirname = os.path.dirname(filepath)

    assert storage.joinpath(dirname).is_dir()


def test_write_json(storage):
    filepath = write("test.txt", {"key": "value"}, data_path=storage)

    with (storage / filepath).open("r") as f:
        assert json.load(f) == {"key": "value"}


def test_get_data_path_for_local_storage():
    mock_file = mock.mock_open(read_data="local")
    with mock.patch.object(Path, "is_file", return_value=True), mock.patch.object(
        Path, "open", mock_file
    ):
        data_path = get_data_path()
        assert isinstance(data_path, PosixPath | WindowsPath)


def test_get_data_path_for_local_storage_sub_folder(config_storage):
    write_config_file(config_storage / "file_backend", "local")
    write_config_file(config_storage / "sub_folder", "sub")
    get_data_path.cache_clear()  # clear cache to avoid test isolation errors
    data_path = get_data_path()
    assert data_path == Path("/symphony_data/sub")


def write_config_file(filepath: Path, content: str | None):
    if content:
        with filepath.open("w") as f:
            f.write(content)


@pytest.mark.skipif(
    "{'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',"
    " 'AWS_BUCKET_NAME', 'AWS_DEFAULT_REGION'} \
    .issubset(os.environ.keys()) == False"
)
def test_get_data_path_for_remote_storage(config_storage):
    # arrange
    write_config_file(
        config_storage / "aws_access_key_id", os.environ["AWS_ACCESS_KEY_ID"]
    )
    write_config_file(
        config_storage / "aws_secret_access_key", os.environ["AWS_SECRET_ACCESS_KEY"]
    )
    write_config_file(config_storage / "aws_bucket_name", os.environ["AWS_BUCKET_NAME"])
    write_config_file(
        config_storage / "aws_default_region", os.environ["AWS_DEFAULT_REGION"]
    )
    write_config_file(
        config_storage / "aws_s3_endpoint_url", os.environ.get("AWS_S3_ENDPOINT_URL")
    )
    write_config_file(config_storage / "file_backend", "S3")

    # act
    data_path = get_data_path()
    assert isinstance(data_path, S3Path)

    filename = f"{uuid.uuid4()}.txt"
    write(filename, "hello", temp_dir=False, data_path=data_path)

    # assert
    session = boto3.session.Session()
    s3 = session.resource("s3", endpoint_url=os.environ.get("AWS_S3_ENDPOINT_URL"))
    bucket = s3.Bucket(os.environ["AWS_BUCKET_NAME"])
    buffer = io.BytesIO()
    bucket.download_fileobj(filename, buffer)
    assert buffer.getvalue().decode("utf-8") == "hello"


def test_get_tls_client_credentials_not_set():
    ca, cert, key = _get_tls_client_credentials()
    assert ca is None
    assert cert is None
    assert key is None


def test_get_tls_client_credentials(tls_storage):
    mocked = dict(CA_CERT="foo", CLIENT_CERT="bar", CLIENT_KEY="baz")
    with mock.patch.dict(os.environ, mocked):
        ca, cert, key = _get_tls_client_credentials()
        assert ca == Path(tls_storage).joinpath("ca.crt")
        assert Path(ca).exists()

        assert cert == Path(tls_storage).joinpath("client.crt")
        assert Path(cert).exists()

        assert key == Path(tls_storage).joinpath("client.key")
        assert Path(key).exists()


def test_get_s3_data_path(tls_storage):
    mocked = dict(
        AWS_BUCKET_NAME="bucket",
        AWS_ACCESS_KEY_ID="access_key",
        AWS_SECRET_ACCESS_KEY="secret",
        AWS_DEFAULT_REGION="fr",
        AWS_S3_ENDPOINT_URL="https://aws-fake_url.com",
        CA_CERT="foo",
        CLIENT_CERT="bar",
        CLIENT_KEY="baz",
    )
    with mock.patch.dict(os.environ, mocked), mock.patch("boto3.resource") as m:
        get_s3_data_path()
        first_call = m.mock_calls[0]
        assert first_call.args == ("s3",)

        config: Config | None = first_call.kwargs.pop("config", None)
        assert config is not None
        assert config.client_cert == (
            Path(tls_storage).joinpath("client.crt"),
            Path(tls_storage).joinpath("client.key"),
        )
        assert first_call.kwargs == {
            "endpoint_url": "https://aws-fake_url.com",
            "verify": Path(tls_storage).joinpath("ca.crt"),
        }
