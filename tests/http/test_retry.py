from sekoia_automation.http.retry import RetryPolicy


def test_retry_policy_create_with_values():
    """Test retry policy creation with values."""

    policy = RetryPolicy.create(
        max_retries=5,
        backoff_factor=0.5,
        status_forcelist=[500, 502],
    )
    assert policy is not None
    assert policy.max_retries == 5
    assert policy.backoff_factor == 0.5
    assert policy.status_forcelist == [500, 502]


def test_retry_policy_create_with_defaults():
    """Test retry policy creation with default values."""

    policy = RetryPolicy.create()
    assert policy is None


def test_retry_policy_create_with_none_max_retries():
    """Test retry policy creation with None max retries."""

    policy = RetryPolicy.create(
        max_retries=None, backoff_factor=0.5, status_forcelist=[500, 502]
    )
    assert policy is not None
    assert policy.max_retries == 3
    assert policy.backoff_factor == 0.5
    assert policy.status_forcelist == [500, 502]


def test_retry_policy_create_with_none_backoff_factor():
    """Test retry policy creation with None backoff factor."""

    policy = RetryPolicy.create(
        max_retries=5, backoff_factor=None, status_forcelist=[500, 502]
    )
    assert policy is not None
    assert policy.max_retries == 5
    assert policy.backoff_factor == 0.1
    assert policy.status_forcelist == [500, 502]


def test_retry_policy_create_with_none_status_forcelist():
    """Test retry policy creation with None status forcelist."""

    policy = RetryPolicy.create(
        max_retries=5, backoff_factor=0.5, status_forcelist=None
    )
    assert policy is not None
    assert policy.max_retries == 5
    assert policy.backoff_factor == 0.5
    assert policy.status_forcelist == [429]


def test_retry_policy_create_with_empty_status_forcelist():
    """Test retry policy creation with empty status forcelist."""

    policy = RetryPolicy.create(max_retries=5, backoff_factor=0.5, status_forcelist=[])
    assert policy is not None
    assert policy.max_retries == 5
    assert policy.backoff_factor == 0.5
    assert policy.status_forcelist == [429]
