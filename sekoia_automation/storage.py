import uuid
from functools import lru_cache
from json.decoder import JSONDecodeError
from pathlib import Path

import boto3
import orjson
from botocore.config import Config
from s3path import S3Path, register_configuration_parameter
from tenacity import retry, stop_after_attempt, wait_exponential

from sekoia_automation import constants
from sekoia_automation.config import TLS_VOLUME_PATH, load_config
from sekoia_automation.utils import capture_retry_error, chunks

FilePath = Path | str
UPLOAD_CHUNK_SIZE = 1024 * 1024 * 50  # 50MB


@lru_cache
@retry(
    reraise=True,
    wait=wait_exponential(max=6),
    stop=stop_after_attempt(10),
    retry_error_callback=capture_retry_error,
)
def get_s3_data_path() -> Path:
    ca_path, cert_path, key_path = _get_tls_client_credentials()
    config = Config()
    if cert_path and key_path:
        config = Config(client_cert=(cert_path, key_path))

    bucket_name = load_config("aws_bucket_name")

    boto3.setup_default_session(
        aws_access_key_id=load_config("aws_access_key_id"),
        aws_secret_access_key=load_config("aws_secret_access_key"),
        aws_session_token=load_config("aws_session_token", non_exist_ok=True),
        region_name=load_config("aws_default_region"),
    )
    base_path = S3Path(f"/{bucket_name}")

    # Allow to use S3 compatible backend (other than AWS)
    endpoint_url = load_config("aws_s3_endpoint_url")
    stack_resource = boto3.resource(
        "s3", endpoint_url=endpoint_url, verify=ca_path, config=config
    )
    register_configuration_parameter(base_path, resource=stack_resource)

    # This will also ensure that credentials are set and valid
    # It will raise NoCredentialsError or something similar in case of failure
    if not base_path.exists():
        raise ValueError("Bucket doesn't exist")
    return base_path


def _get_tls_client_credentials() -> tuple[Path | None, Path | None, Path | None]:
    """
    Get the TLS client credentials if set. It returns the path to:
        * The certificate authority certificate
        * The client certificate
        * The client private key

    The cryptographic material is loaded from the following env variables/files:
        * CLIENT_CERT/client_cert
        * CLIENT_KEY/client_key
        * CA_CERT/ca_cert

    In order to be usable by the botocore lib the data is saved in the following files:
        * client.crt
        * client.key
        * ca.crt
    """
    volume = Path(TLS_VOLUME_PATH)
    volume.mkdir(parents=True, exist_ok=True)

    ca_path = None
    if ca_cert := load_config("ca_cert", non_exist_ok=True):
        ca_path = volume.joinpath("ca.crt")
        ca_path.write_text(ca_cert)

    cert_path = None
    if client_cert := load_config("client_cert", non_exist_ok=True):
        cert_path = volume.joinpath("client.crt")
        cert_path.write_text(client_cert)

    key_path = None
    if client_key := load_config("client_key", non_exist_ok=True):
        key_path = volume.joinpath("client.key")
        key_path.write_text(client_key)

    return ca_path, cert_path, key_path


def get_local_data_path() -> Path:
    return Path(constants.DATA_STORAGE)


@lru_cache
def get_data_path() -> Path:
    """Returns the Path object to use to manipulate files.

    It can be either an S3 Path or a regular one.

    If it is a S3 path it makes sure that the bucket exists
    and at the same time that the credentials are valid.

    For configuration options see
    https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html
    """
    file_backend = load_config("file_backend", non_exist_ok=True)
    if file_backend is None or file_backend.upper() != "S3":
        path = get_local_data_path()
    else:
        path = get_s3_data_path()

    sub_folder = load_config("sub_folder", non_exist_ok=True)
    if sub_folder:
        path = path / sub_folder
    return path


class PersistentJSON:
    """This class can be used to easily synchronize JSON Serializable dicts
    with files on disk.

    It can be used as a faster / less risky alternative to `shelve` when
    the dict is JSON Serializable.

    Args:
    ----
        filepath (str): path of the JSON file used to persist data.
    """

    def __init__(self, filepath: FilePath, data_path: Path | None = None):
        filepath = filepath if isinstance(filepath, Path) else Path(filepath)
        data_path = data_path or get_data_path()

        if filepath.is_absolute():
            self._filepath = filepath
        else:
            self._filepath = data_path / filepath

        self._data: dict = {}

    @retry(
        reraise=True,
        wait=wait_exponential(max=6),
        stop=stop_after_attempt(10),
        retry_error_callback=capture_retry_error,
    )
    def load(self):
        if not self._data and self._filepath.is_file():
            with self._filepath.open("r") as fd:
                try:
                    self._data = orjson.loads(fd.read().encode("utf-8"))
                except JSONDecodeError:
                    # The content is not valid json
                    self._data = {}

    @retry(
        reraise=True,
        wait=wait_exponential(max=6),
        stop=stop_after_attempt(10),
        retry_error_callback=capture_retry_error,
    )
    def dump(self):
        with self._filepath.open("wb") as out:
            data = orjson.dumps(self._data)
            for chunk in chunks(data, UPLOAD_CHUNK_SIZE):
                out.write(chunk)

    def __enter__(self):
        self.load()

        return self._data

    def __exit__(self, _, __, ___):
        self.dump()


@retry(
    reraise=True,
    wait=wait_exponential(max=6),
    stop=stop_after_attempt(10),
    retry_error_callback=capture_retry_error,
)
def temp_directory(data_path: Path | None = None) -> str:
    """Create a temporary directory inside data storage.

    Returns
    -------
        str: The name of the created directory.
    """
    data_path = data_path or get_data_path()
    name: str = str(uuid.uuid4())
    (data_path / name).mkdir(parents=True, exist_ok=True)

    return name


@retry(
    reraise=True,
    wait=wait_exponential(max=6),
    stop=stop_after_attempt(10),
    retry_error_callback=capture_retry_error,
)
def write(
    filename: str,
    content: dict | str,
    temp_dir: bool = True,
    data_path: Path | None = None,
) -> Path:
    """Write content to a file inside data Storage.

    Args:
        filename (str): name of the file to write data to.
        content (str/dict): content to write to the file.
        temp_dir (bool): set to False if there is no need to create
        a temporary directory for the file.

    Returns
    -------
        str: path of the file, relative to data Storage
    """
    data_path = data_path or get_data_path()
    directory: Path = data_path

    if temp_dir:
        directory = directory / temp_directory(data_path=data_path)

    filepath = directory.joinpath(filename)

    if isinstance(content, str):
        data = content.encode("utf-8")
    else:
        data = orjson.dumps(content)
    with filepath.open("wb") as out:
        for chunk in chunks(data, UPLOAD_CHUNK_SIZE):
            out.write(chunk)

    return filepath.relative_to(data_path)
