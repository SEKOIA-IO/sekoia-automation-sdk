import threading
from abc import ABCMeta, abstractmethod


class MetricsExporterThread(threading.Thread, metaclass=ABCMeta):
    @abstractmethod
    def run(self):
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def create(cls, *args, **kwargs):
        raise NotImplementedError
