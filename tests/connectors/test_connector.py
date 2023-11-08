import os
from unittest.mock import Mock, PropertyMock, patch

import pytest
from tenacity import Retrying, stop_after_attempt, wait_none

from sekoia_automation.connector import Connector, DefaultConnectorConfiguration
from sekoia_automation.constants import CHUNK_BYTES_MAX_SIZE, EVENT_BYTES_MAX_SIZE
from sekoia_automation.exceptions import TriggerConfigurationError
from sekoia_automation.module import Module
from sekoia_automation.trigger import Trigger
from tests.utils import match_events

EVENTS = ["foo", "bar"]


class DummyConnector(Connector):
    def run(self):
        raise NotImplementedError


@pytest.fixture
def test_connector(storage, mocked_trigger_logs):
    with patch("sentry_sdk.set_tag"):
        test_connector = DummyConnector(data_path=storage)
        test_connector.send_event = Mock()

        test_connector.trigger_activation = "2022-03-14T11:16:14.236930Z"
        test_connector.configuration = {"intake_key": ""}

        test_connector.log = Mock()
        test_connector.log_exception = Mock()

        yield test_connector

        test_connector.stop()


def test_check_http_default_headers(test_connector):
    test_connector.module._manifest = {
        "slug": "dummyslug",
        "version": "dummyversion",
    }

    assert test_connector.http_default_headers == {
        "User-Agent": "sekoiaio-connector/dummyslug-dummyversion"
    }


def test_forward_events(test_connector):
    test_connector.forward_events(events=EVENTS)
    test_connector.send_event.assert_called_once()

    test_connector.send_records = Mock()
    test_connector.forward_events(events=EVENTS)
    test_connector.send_records.assert_called_once_with(
        records=["foo", "bar"], event_name="dummyconnector_00:00:00"
    )


def test_send_records_to_file(test_connector):
    event_name = "baz"
    test_connector.send_records(records=EVENTS, event_name=event_name, to_file=True)
    test_connector.send_event.assert_called_once()


def test_send_records(test_connector):
    event_name = "baz"
    test_connector.send_records(records=EVENTS, event_name=event_name, to_file=False)
    test_connector.send_event.assert_called_once()


def test_chunk_events(test_connector):
    with patch("sekoia_automation.connector.CHUNK_BYTES_MAX_SIZE", 4):  # len("foo") + 1
        chunks = test_connector._chunk_events(events=EVENTS)
        chunk_number = 0

        for chunk in chunks:
            assert "".join(chunk) in EVENTS
            chunk_number += 1

    assert chunk_number == 2


def test_chunk_events_exceed_size(test_connector):
    events_a = ["a" * EVENT_BYTES_MAX_SIZE] * int(
        CHUNK_BYTES_MAX_SIZE / EVENT_BYTES_MAX_SIZE
    )
    events_b = ["b"]
    events = events_a + events_b
    chunks = list(test_connector._chunk_events(events=events))
    assert len(chunks) == 2
    assert chunks == [events_a, events_b]


def test_chunk_events_discard_too_long_message(test_connector):
    event_a = "a" * EVENT_BYTES_MAX_SIZE
    event_b = "b" * (EVENT_BYTES_MAX_SIZE + 1)
    event_c = "c"
    events = [event_a, event_b, event_c]
    chunks = list(test_connector._chunk_events(events=events))
    assert len(chunks) == 1
    assert chunks == [[event_a, event_c]]
    assert test_connector.log.called


def test_push_event_to_intake_with_2_events(test_connector, mocked_trigger_logs):
    url = "https://intake.sekoia.io/batch"
    mocked_trigger_logs.post(url, json={"event_ids": ["001", "002"]})
    result = test_connector.push_events_to_intakes(EVENTS)
    assert result is not None
    assert len(result) == 2
    assert result == ["001", "002"]


def test_push_event_to_intake_with_chunks(test_connector, mocked_trigger_logs):
    url = "https://intake.sekoia.io/batch"
    mocked_trigger_logs.post(
        url, json={"event_ids": ["001"]}, additional_matcher=match_events("foo")
    )
    mocked_trigger_logs.post(
        url, json={"event_ids": ["002"]}, additional_matcher=match_events("bar")
    )
    mocked_trigger_logs.post(
        url, json={"event_ids": ["003"]}, additional_matcher=match_events("baz")
    )
    mocked_trigger_logs.post(
        url, json={"event_ids": ["004"]}, additional_matcher=match_events("oof")
    )
    with patch("sekoia_automation.connector.CHUNK_BYTES_MAX_SIZE", 4):  # len("foo") + 1
        result = test_connector.push_events_to_intakes(["foo", "bar", "baz", "oof"])

    assert result is not None
    assert len(result) == 4
    assert mocked_trigger_logs.call_count == 4
    assert result == ["001", "002", "003", "004"]


def test_push_event_to_intake_custom_url(test_connector, mocked_trigger_logs):
    url = "https://fra2.app.sekoia.io/v1/intake-http/batch"
    batch_mock = mocked_trigger_logs.post(
        url, json={"event_ids": ["001"]}, additional_matcher=match_events("foo")
    )
    # With trailing slash
    with patch.dict(
        os.environ, {"INTAKE_URL": "https://fra2.app.sekoia.io/v1/intake-http/"}
    ):
        test_connector.push_events_to_intakes(["foo"])
        assert batch_mock.call_count == 1

    # Without trailing slash
    mocked_trigger_logs.reset_mock()
    with patch.dict(
        os.environ, {"INTAKE_URL": "https://fra2.app.sekoia.io/v1/intake-http"}
    ):
        test_connector.push_events_to_intakes(["foo"])
        assert batch_mock.call_count == 1


def test_push_event_to_intake_with_chunks_executor_stopped(
    test_connector, mocked_trigger_logs
):
    test_connector.stop()
    url = "https://intake.sekoia.io/batch"
    mocked_trigger_logs.post(
        url, json={"event_ids": ["001"]}, additional_matcher=match_events("foo")
    )
    mocked_trigger_logs.post(
        url, json={"event_ids": ["002"]}, additional_matcher=match_events("bar")
    )
    mocked_trigger_logs.post(
        url, json={"event_ids": ["003"]}, additional_matcher=match_events("baz")
    )
    mocked_trigger_logs.post(
        url, json={"event_ids": ["004"]}, additional_matcher=match_events("oof")
    )
    with patch("sekoia_automation.connector.CHUNK_BYTES_MAX_SIZE", 4):  # len("foo") + 1
        result = test_connector.push_events_to_intakes(["foo", "bar", "baz", "oof"])
    assert result is not None
    assert len(result) == 4
    assert mocked_trigger_logs.call_count == 4
    assert result == ["001", "002", "003", "004"]


def test_push_events_to_intakes_no_events(test_connector):
    result = test_connector.push_events_to_intakes([])
    assert result == []


def test_push_events_to_intakes_api_failed(test_connector, mocked_trigger_logs):
    url = "https://intake.sekoia.io/batch"
    mocked_trigger_logs.post(url, status_code=504)
    test_connector._retry = lambda: Retrying(
        reraise=True,
        stop=stop_after_attempt(1),
    )
    result = test_connector.push_events_to_intakes(EVENTS)
    assert result == []


def test_push_events_to_intakes_api_failed_retried(test_connector, mocked_trigger_logs):
    url = "https://intake.sekoia.io/batch"
    mocked_trigger_logs.post(
        url,
        [
            {"status_code": 504},
            {"json": {"event_ids": ["001", "002"]}, "status_code": 200},
        ],
    )
    test_connector._retry = lambda: Retrying(
        reraise=True, stop=stop_after_attempt(5), wait=wait_none()
    )
    result = test_connector.push_events_to_intakes(EVENTS)
    assert result == ["001", "002"]


def test_push_events_to_intake_invalid_intake_key(test_connector):
    with pytest.raises(TriggerConfigurationError):
        test_connector.configuration = {"intake_key": None}


def test_query_exception_api(test_connector, requests_mock):
    requests_mock.post(
        "https://intake.sekoia.io/batch",
        [
            {"exc": Exception},
            {"json": {"event_ids": ["001", "002"]}},
        ],
    )
    test_connector._retry = lambda: Retrying(reraise=True)
    assert test_connector.push_events_to_intakes(EVENTS) == ["001", "002"]


def test_connector_configuration(test_connector):
    test_connector._configuration = None
    config = DefaultConnectorConfiguration(intake_key="foo")
    with patch.object(
        Module, "load_config", return_value=config
    ) as mock_load_config, patch("sentry_sdk.set_context") as mock_set_sentry_context:
        assert test_connector.configuration == config
        mock_set_sentry_context.assert_called_with(
            "connector_configuration", config.dict()
        )
        mock_load_config.assert_called_with(
            test_connector.CONNECTOR_CONFIGURATION_FILE_NAME, "json"
        )


def test_connector_configuration_file_not_found(test_connector):
    test_connector._configuration = None
    config = "foo"
    with patch.object(
        Trigger, "configuration", new_callable=PropertyMock, return_value=config
    ):
        assert test_connector.configuration == config
