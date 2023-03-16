from http.server import HTTPServer

from prometheus_client.exposition import MetricsHandler
from prometheus_client.registry import REGISTRY, CollectorRegistry

from sekoia_automation.metrics.base import MetricsExporterThread


class PrometheusExporterThread(MetricsExporterThread):
    """A thread clast that holds an http and makes it serve_forever()."""

    def __init__(self, httpd, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.httpd = httpd

    @property
    def listening_address(self) -> tuple[str, int]:
        "Return the listening address and port of the server"
        return self.httpd.server_address

    def run(self):
        self.httpd.serve_forever()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    @classmethod
    def create(
        cls, port: int, addr: str = "0.0.0.0", registry: CollectorRegistry = REGISTRY
    ) -> "PrometheusExporterThread":
        """
        Create a stoppable Prometheus HTTP metrics exporter
        """
        httpd = HTTPServer((addr, port), MetricsHandler.factory(registry))
        exporter = cls(httpd)
        exporter.daemon = True
        return exporter
