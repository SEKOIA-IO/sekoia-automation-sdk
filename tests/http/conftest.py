import pytest


@pytest.fixture
def auth_url(session_faker):
    """
    Fixture to initialize auth_url.

    Returns:
        str:
    """
    return session_faker.uri()


@pytest.fixture
def base_url(session_faker):
    """
    Fixture to initialize base_url.

    Returns:
        str:
    """
    return session_faker.uri()
