from sekoia_automation.configuration import get_configuration, Configuration


configuration: Configuration = get_configuration()


def load_config(name: str, type_: str = "str", non_exist_ok: bool = False):
    return configuration.load(name, type_, non_exist_ok)
