from functools import cached_property

from prometheus_client import Counter, Gauge, Histogram


class MetricsMixin:
    _prometheus_namespace = "symphony_module_common"

    _forwarded_events: Counter | None = None
    _forward_events_duration: Histogram | None = None
    _discarded_events: Counter | None = None
    _events_lag: Gauge | None = None

    @cached_property
    def forwarded_events_counter(self) -> Counter | None:
        """
        Get forwarded events counter.

        Returns:
            Counter | None:
        """
        if self._forwarded_events is None:
            try:
                self._forwarded_events = Counter(
                    name="forwarded_events",
                    documentation="Number of events forwarded to Sekoia.io",
                    namespace=self._prometheus_namespace,
                    labelnames=["intake_key"],
                )
            except Exception:
                return None

        return self._forwarded_events

    @cached_property
    def forward_events_duration(self) -> Histogram | None:
        """
        Get forward events duration.

        Returns:
            Histogram | None:
        """
        if self._forward_events_duration is None:
            try:
                self._forward_events_duration = Histogram(
                    name="forward_events_duration",
                    documentation="Duration of the forward events",
                    namespace=self._prometheus_namespace,
                    labelnames=["intake_key"],
                )
            except Exception:
                return None

        return self._forward_events_duration

    @cached_property
    def discarded_events_counter(self) -> Counter | None:
        """
        Get discarded events counter.

        Returns:
            Counter | None:
        """
        if self._discarded_events is None:
            try:
                self._discarded_events = Counter(
                    name="discarded_events",
                    documentation="Number of events discarded from the collect",
                    namespace=self._prometheus_namespace,
                    labelnames=["intake_key"],
                )
            except Exception:
                return None

        return self._discarded_events

    @cached_property
    def events_lag(self) -> Gauge | None:
        """
        Get events lag gauge.

        Returns:
            Gauge | None:
        """
        if self._events_lag is None:
            try:
                self._events_lag = Gauge(
                    name="events_lags",
                    documentation="The delay (seconds) from the date of the last event",
                    namespace=self._prometheus_namespace,
                    labelnames=["intake_key"],
                )
            except Exception:
                return None

        return self._events_lag

    def put_forward_events_duration(self, intake_key: str, duration: float) -> None:
        """
        Put forwarded events duration.

        Args:
            intake_key: str
            duration: float
        """
        if self.forward_events_duration:
            self.forward_events_duration.labels(intake_key=intake_key).observe(duration)

    def put_discarded_events(self, intake_key: str, count: int) -> None:
        """
        Put discarded events.

        Args:
            intake_key: str
            count: int
        """
        if self.discarded_events_counter:
            self.discarded_events_counter.labels(intake_key=intake_key).inc(count)

    def put_forwarded_events(self, intake_key: str, count: int) -> None:
        """
        Put forwarded events.

        Args:
            intake_key: str
            count: int
        """
        if self.forwarded_events_counter:
            self.forwarded_events_counter.labels(intake_key=intake_key).inc(count)

    def put_events_lag(self, intake_key: str, lag: float) -> None:
        """
        Put events lag.

        Args:
            intake_key: str
            lag: float
        """
        if self.events_lag:
            self.events_lag.labels(intake_key=intake_key).set(lag)
