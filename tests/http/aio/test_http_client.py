"""Async HTTP client tests."""

import json
import time

import pytest
from aioresponses import aioresponses
from faker import Faker

from sekoia_automation.http.aio.http_client import AsyncHttpClient


@pytest.mark.asyncio
async def test_simple_workflow_async_http_client(base_url: str, session_faker: Faker):
    """
    Test simple workflow of AsyncHttpClient.

    Args:
        base_url: str
        session_faker: Faker
    """
    client = AsyncHttpClient.create()

    data = session_faker.json(
        data_columns={"test": ["name", "name", "name"]},
        num_rows=10,
    )

    with aioresponses() as mocked_responses:
        mocked_responses.get(
            url=base_url,
            status=200,
            body=data,
            headers={"Content-Length": f"{len(data)}"},
        )

        async with client.session() as session:
            async with session.get(base_url) as response:
                assert response.status == 200
                assert await response.json() == json.loads(data)


@pytest.mark.asyncio
async def test_rate_limited_workflow_async_http_client(
    base_url: str, session_faker: Faker
):
    """
    Test simple workflow of AsyncHttpClient.

    Args:
        base_url: str
        session_faker: Faker
    """
    client = AsyncHttpClient.create(max_rate=1, time_period=1)

    data = session_faker.json(
        data_columns={"test": ["name", "name", "name"]},
        num_rows=10,
    )

    with aioresponses() as mocked_responses:
        time_start = time.time()
        for _ in range(3):
            mocked_responses.get(
                url=base_url,
                status=200,
                body=data,
                headers={"Content-Length": f"{len(data)}"},
            )

            async with client.session() as session:
                async with session.get(base_url) as response:
                    assert response.status == 200
                    assert await response.json() == json.loads(data)

        time_end = time.time()

        assert time_end - time_start >= 2


@pytest.mark.asyncio
async def test_rate_limited_workflow_async_http_client_1(
    base_url: str, session_faker: Faker
):
    """
    Test simple workflow of AsyncHttpClient.

    Args:
        base_url: str
        session_faker: Faker
    """
    client = AsyncHttpClient.create(max_rate=1, time_period=1)

    data = session_faker.json(
        data_columns={"test": ["name", "name", "name"]},
        num_rows=10,
    )

    with aioresponses() as mocked_responses:
        time_start = time.time()
        for _ in range(3):
            mocked_responses.get(
                url=base_url,
                status=200,
                body=data,
                headers={"Content-Length": f"{len(data)}"},
            )

            async with client.session() as session:
                async with session.get(base_url) as response:
                    assert response.status == 200
                    assert await response.json() == json.loads(data)

        time_end = time.time()

        assert time_end - time_start >= 2


@pytest.mark.asyncio
async def test_retry_workflow_get_async_http_client(
    base_url: str, session_faker: Faker
):
    """
    Test simple workflow of AsyncHttpClient.

    Args:
        base_url: str
        session_faker: Faker
    """
    status_1 = session_faker.random.randint(400, 500)
    status_2 = session_faker.random.randint(400, 500)
    status_3 = session_faker.random.randint(400, 500)

    client = AsyncHttpClient.create(
        max_retries=3,
        backoff_factor=0.1,
        status_forcelist=[status_1, status_2, status_3],
    )

    with aioresponses() as mocked_responses:
        # Test GET requests
        mocked_responses.get(url=base_url, status=status_1)
        mocked_responses.get(url=base_url, status=status_2)
        mocked_responses.get(url=base_url, status=status_3)

        async with client.request_retry("GET", base_url) as response:
            # As a result, the last response should be 412
            assert response.status == status_3

        mocked_responses.get(url=base_url, status=status_1)
        mocked_responses.get(url=base_url, status=status_2)
        mocked_responses.get(url=base_url, status=status_3)

        async with client.get(base_url) as response:
            # As a result, the last response should be 412
            assert response.status == status_3


@pytest.mark.asyncio
async def test_retry_workflow_post_async_http_client(
    base_url: str, session_faker: Faker
):
    """
    Test simple workflow of AsyncHttpClient.

    Args:
        base_url: str
        session_faker: Faker
    """
    status_1 = session_faker.random.randint(400, 500)
    status_2 = session_faker.random.randint(400, 500)
    status_3 = session_faker.random.randint(400, 500)

    client = AsyncHttpClient.create(
        max_retries=3,
        backoff_factor=0.1,
        status_forcelist=[status_1, status_2, status_3],
    )

    data = json.loads(
        session_faker.json(
            data_columns={"test": ["name", "name", "name"]},
            num_rows=10,
        )
    )

    with aioresponses() as mocked_responses:
        # Test POST requests
        mocked_responses.post(url=base_url, payload=data, status=status_1)
        mocked_responses.post(url=base_url, payload=data, status=status_2)
        mocked_responses.post(url=base_url, payload=data, status=status_3)

        async with client.request_retry("POST", base_url, json=data) as response:
            assert response.status == status_3

        mocked_responses.post(url=base_url, payload=data, status=status_1)
        mocked_responses.post(url=base_url, payload=data, status=status_2)
        mocked_responses.post(url=base_url, payload=data, status=status_3)

        async with client.post(base_url, json=data) as response:
            assert response.status == status_3


@pytest.mark.asyncio
async def test_retry_workflow_put_async_http_client(
    base_url: str, session_faker: Faker
):
    """
    Test simple workflow of AsyncHttpClient.

    Args:
        base_url: str
        session_faker: Faker
    """
    status_1 = session_faker.random.randint(400, 500)
    status_2 = session_faker.random.randint(400, 500)
    status_3 = session_faker.random.randint(400, 500)

    client = AsyncHttpClient.create(
        max_retries=3,
        backoff_factor=0.1,
        status_forcelist=[status_1, status_2, status_3],
    )

    data = json.loads(
        session_faker.json(
            data_columns={"test": ["name", "name", "name"]},
            num_rows=10,
        )
    )

    with aioresponses() as mocked_responses:
        # Test PUT requests
        mocked_responses.put(url=base_url, payload=data, status=status_1)
        mocked_responses.put(url=base_url, payload=data, status=status_2)
        mocked_responses.put(url=base_url, payload=data, status=status_3)

        async with client.request_retry("PUT", base_url, json=data) as response:
            assert response.status == status_3

        mocked_responses.put(url=base_url, payload=data, status=status_1)
        mocked_responses.put(url=base_url, payload=data, status=status_2)
        mocked_responses.put(url=base_url, payload=data, status=status_3)

        async with client.put(base_url, json=data) as response:
            assert response.status == status_3


@pytest.mark.asyncio
async def test_retry_workflow_head_async_http_client(
    base_url: str, session_faker: Faker
):
    """
    Test simple workflow of AsyncHttpClient.

    Args:
        base_url: str
        session_faker: Faker
    """
    status_1 = session_faker.random.randint(400, 500)
    status_2 = session_faker.random.randint(400, 500)
    status_3 = session_faker.random.randint(400, 500)

    client = AsyncHttpClient.create(
        max_retries=3,
        backoff_factor=0.1,
        status_forcelist=[status_1, status_2, status_3],
    )

    with aioresponses() as mocked_responses:
        # Test HEAD requests
        mocked_responses.head(url=base_url, status=status_1)
        mocked_responses.head(url=base_url, status=status_2)
        mocked_responses.head(url=base_url, status=status_3)

        async with client.request_retry("HEAD", base_url) as response:
            assert response.status == status_3

        mocked_responses.head(url=base_url, status=status_1)
        mocked_responses.head(url=base_url, status=status_2)
        mocked_responses.head(url=base_url, status=status_3)

        async with client.head(base_url) as response:
            assert response.status == status_3


@pytest.mark.asyncio
async def test_retry_workflow_delete_async_http_client(
    base_url: str, session_faker: Faker
):
    """
    Test simple workflow of AsyncHttpClient.

    Args:
        base_url: str
        session_faker: Faker
    """
    status_1 = session_faker.random.randint(400, 500)
    status_2 = session_faker.random.randint(400, 500)
    status_3 = session_faker.random.randint(400, 500)

    client = AsyncHttpClient.create(
        max_retries=3,
        backoff_factor=0.1,
        status_forcelist=[status_1, status_2, status_3],
    )

    with aioresponses() as mocked_responses:
        # Test DELETE requests
        mocked_responses.delete(url=base_url, status=status_1)
        mocked_responses.delete(url=base_url, status=status_2)
        mocked_responses.delete(url=base_url, status=status_3)

        async with client.request_retry("delete", base_url) as response:
            assert response.status == status_3

        mocked_responses.delete(url=base_url, status=status_1)
        mocked_responses.delete(url=base_url, status=status_2)
        mocked_responses.delete(url=base_url, status=status_3)

        async with client.delete(base_url) as response:
            assert response.status == status_3


@pytest.mark.asyncio
async def test_retry_workflow_patch_async_http_client(
    base_url: str, session_faker: Faker
):
    """
    Test simple workflow of AsyncHttpClient.

    Args:
        base_url: str
        session_faker: Faker
    """
    status_1 = session_faker.random.randint(400, 500)
    status_2 = session_faker.random.randint(400, 500)
    status_3 = session_faker.random.randint(400, 500)

    client = AsyncHttpClient.create(
        max_retries=3,
        backoff_factor=0.1,
        status_forcelist=[status_1, status_2, status_3],
    )

    with aioresponses() as mocked_responses:
        # Test PATCH requests
        mocked_responses.patch(url=base_url, status=status_1)
        mocked_responses.patch(url=base_url, status=status_2)
        mocked_responses.patch(url=base_url, status=status_3)

        async with client.request_retry("PATCH", base_url) as response:
            assert response.status == status_3

        mocked_responses.patch(url=base_url, status=status_1)
        mocked_responses.patch(url=base_url, status=status_2)
        mocked_responses.patch(url=base_url, status=status_3)

        async with client.patch(base_url) as response:
            assert response.status == status_3


@pytest.mark.asyncio
async def test_complete_configurable_async_http_client(
    base_url: str, session_faker: Faker
):
    """
    Test complete configurable AsyncHttpClient.

    Args:
        base_url:
    """
    status_1 = session_faker.random.randint(400, 500)
    status_2 = session_faker.random.randint(400, 500)
    status_3 = session_faker.random.randint(400, 500)

    client = AsyncHttpClient.create(
        max_rate=1,
        time_period=1,
        max_retries=3,
        backoff_factor=0.1,
        status_forcelist=[status_1, status_2, status_3],
    )

    data = session_faker.json(
        data_columns={"test": ["name", "name", "name"]},
        num_rows=10,
    )

    with aioresponses() as mocked_responses:
        # Test POST requests
        mocked_responses.get(url=base_url, status=status_1)
        mocked_responses.get(url=base_url, status=status_2)
        mocked_responses.get(
            url=base_url,
            status=200,
            body=data.encode("utf-8"),
        )

        start_time = time.time()
        async with client.get(base_url) as response:
            assert response.status == 200
            assert await response.text() == data
            end_time = time.time()

        assert end_time - start_time >= 2

        mocked_responses.get(url=base_url, status=status_1)
        mocked_responses.get(url=base_url, status=status_1)
        mocked_responses.get(url=base_url, status=status_1)
        mocked_responses.get(url=base_url, status=status_1)
        start_time = time.time()
        async with client.get(base_url) as response:
            assert response.status == status_1
            end_time = time.time()

        assert end_time - start_time >= 3
