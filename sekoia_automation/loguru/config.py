"""Logging configuration and init function."""

import logging
import sys

from loguru import logger
from pydantic import BaseModel, validator

from .formatters import format_record
from .handlers import InterceptHandler


class LoggingConfig(BaseModel):
    """Contain all necessary logging config."""

    log_lvl: str = "INFO"

    log_file: str = "logs/{time:YYYY-MM-DD}.log"
    log_rotation: str = "00:00"
    log_retention: str = "1 month"
    log_compression: str = "zip"
    log_queue: bool = True

    json_logs: bool = False

    loguru_format: str = "".join(
        [
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | ",
            "<level>{level: <5}</level> | ",
            "<level>{message}</level>",
        ],
    )

    @classmethod
    @validator("log_lvl", pre=True)
    def assemble_log_lvl(cls, log_lvl: str) -> str:  # pragma: no cover
        """
        Format and validate log lvl str.

        Args:
            log_lvl: str

        Returns:
            str:

        Raises:
            ValueError: if input string is invalid
        """
        upper_str = log_lvl.upper()
        if isinstance(logging.getLevelName(upper_str), str):
            raise ValueError(f"Incorrect log lvl variable {log_lvl}")

        return upper_str


def init_logging(log_conf: LoggingConfig = LoggingConfig()) -> None:
    """
    Replace logging handlers with a custom handler.

    This function should be called at application startup in the beginning.
    Example:
    >>> from sekoia_automation.helpers.loguru.config import init_logging
    >>> if __name__ == "__main__":
    >>>     init_logging()
    >>> # Other part of application
    >>> from loguru import logger
    >>> ...
    >>> logger.info("Log message formatted {one} {two}", one="First", two="Second")

    Args:
        log_conf: LoggingConfig

    Returns:
        LoggingConfig:
    """
    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(log_conf.log_lvl)

    for name in logging.root.manager.loggerDict.keys():
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True

    logger.configure(
        handlers=[
            {
                "sink": sys.stdout,
                "serialize": log_conf.json_logs,
                "format": lambda values: format_record(
                    values,
                    log_conf.loguru_format,
                ),
            },
        ],
    )
