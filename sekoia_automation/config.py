from sekoia_automation.configuration import Configuration, get_configuration

configuration: Configuration = get_configuration()


def load_config(name: str, type_: str = "str", non_exist_ok: bool = False):
    return configuration.load(name, type_, non_exist_ok)
