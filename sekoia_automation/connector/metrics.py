from prometheus_client import Counter, Gauge, Histogram


class MetricsMixin:
    _prometheus_namespace = "symphony_module_common"

    _outcoming_events: Counter = Counter(
        name="forwarded_events",
        documentation="Number of events forwarded to Sekoia.io",
        namespace=_prometheus_namespace,
        labelnames=["intake_key"],
    )

    _forward_events_duration: Histogram = Histogram(
        name="forward_events_duration",
        documentation="Duration to collect and forward events from eventhub",
        namespace=_prometheus_namespace,
        labelnames=["intake_key"],
    )

    _discarded_events: Counter = Counter(
        name="discarded_events",
        documentation="Number of events discarded from the collect",
        namespace=_prometheus_namespace,
        labelnames=["intake_key"],
    )

    _events_lag: Gauge = Gauge(
        name="events_lags",
        documentation="The delay, in seconds, from the date of the last event",
        namespace=_prometheus_namespace,
        labelnames=["intake_key"],
    )
