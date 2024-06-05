import time

import requests_mock
from requests import Session
from requests.adapters import HTTPAdapter

from sekoia_automation.http.sync.http_client import SyncHttpClient


def test_simple_workflow_sync_http_client(base_url: str):
    """
    Test simple workflow of SyncHttpClient.

    Args:
        base_url: str
    """
    client = SyncHttpClient.create()

    with requests_mock.Mocker() as m:
        m.get(base_url, status_code=404)

        session = client.session()
        assert isinstance(session, Session)
        adapter = session.adapters["http://"]

        assert isinstance(adapter, HTTPAdapter)
        assert adapter.max_retries.total == 0

        response = session.get(base_url)
        assert response.status_code == 404


def test_simple_workflow_sync_http_client_rate_limit(base_url: str):
    """
    Test simple workflow of SyncHttpClient with rate limit.

    Args:
        base_url:
    """
    # 1 request per second
    client = SyncHttpClient.create(max_rate=1, time_period=1)

    with requests_mock.Mocker() as m:
        m.get(base_url, text="123", status_code=429)
        session = client.session()

        start = time.time()
        for _ in range(3):
            session.get(base_url)

        end = time.time()

        assert end - start >= 2


def test_simple_workflow_sync_http_client_retry(base_url: str):
    """
    Test simple workflow of SyncHttpClient with retry.

    Args:
        base_url:
    """
    # 1 request per second
    client = SyncHttpClient.create(
        max_retries=5, backoff_factor=0.1, status_forcelist=[500]
    )

    with requests_mock.Mocker() as m:
        m.get(base_url, text="123", status_code=500)

        session = client.session()
        response = session.get(base_url)

        # It should fail anyway
        assert response.status_code == 500


def test_complete_configurable_http_client(base_url: str):
    """
    Test complete configurable SyncHttpClient.

    Args:
        base_url:
    """
    client = SyncHttpClient.create(
        max_rate=1,
        time_period=1,
        max_retries=5,
        backoff_factor=100,
        status_forcelist=[400],
    )

    with requests_mock.Mocker() as m:
        m.get(base_url, text="123", status_code=400)

        session = client.session()
        start = time.time()
        for _ in range(3):
            response = session.get(base_url)
            # It should fail anyway
            assert response.status_code == 400

        end = time.time()

        assert end - start >= 2
