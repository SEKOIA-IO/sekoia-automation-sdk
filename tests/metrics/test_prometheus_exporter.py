import requests
from prometheus_client import CollectorRegistry, Counter

from sekoia_automation.metrics import PrometheusExporterThread, make_exporter


def test_prometheus_exporter():
    exporter_class = PrometheusExporterThread
    registry = CollectorRegistry()
    counter = Counter(
        name="counter",
        namespace="namespace",
        labelnames=["label"],
        registry=registry,
        documentation="A simple counter",
    )
    counter.labels(label="label1").inc(42)

    exporter = make_exporter(exporter_class, 0, registry=registry)
    exporter.start()
    (address, port) = exporter.listening_address

    response = requests.get(f"http://{address}:{port}/metrics")
    exporter.stop()
    assert b'namespace_counter_total{label="label1"} 42.0' in response.content
