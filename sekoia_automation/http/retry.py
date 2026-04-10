from typing import Optional

from pydantic import BaseModel


class RetryPolicy(BaseModel):
    """Retry policy for http requests."""

    max_retries: int
    backoff_factor: float
    status_forcelist: list[int]

    @classmethod
    def create(
        cls,
        max_retries: int | None = None,
        backoff_factor: float | None = None,
        status_forcelist: list[int] | None = None,
    ) -> Optional["RetryPolicy"]:
        """
        Create retry policy configuration.

        All parameters are optional.
        If all the parameters is None, the function will return None.
        Otherwise, it will return a RetryPolicy object.

        Default values:
            - max_retries: 0
            - backoff_factor: 0.1
            - status_forcelist: []

        Args:
            max_retries: int | None
            backoff_factor: float | None
            status_forcelist: list[int] | None

        Returns:
            Optional["RetryPolicy"]:
        """
        if not max_retries and not backoff_factor and not status_forcelist:
            return None

        return cls(
            max_retries=max_retries or 3,
            backoff_factor=backoff_factor or 0.1,
            status_forcelist=status_forcelist or [429],
        )
