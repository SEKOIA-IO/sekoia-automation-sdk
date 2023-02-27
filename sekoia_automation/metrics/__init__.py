from sekoia_automation.metrics.base import MetricsExporterThread
from sekoia_automation.metrics.prometheus import PrometheusExporterThread


def make_exporter(
    klass: type[MetricsExporterThread], *args, **kwargs
) -> MetricsExporterThread:
    """
    Create a stoppable metrics exporter
    """
    return klass.create(*args, **kwargs)


__all__ = ["PrometheusExporterThread", "make_exporter"]
