from abc import ABC, abstractmethod


class Configuration(ABC):
    @abstractmethod
    def load(self, name: str, type_: str = "str", non_exist_ok=False):
        pass

    @abstractmethod
    def __hash__(self):
        pass
