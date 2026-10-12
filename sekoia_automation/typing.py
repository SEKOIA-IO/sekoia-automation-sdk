from typing import Annotated, Literal

from pydantic import StringConstraints

SupportedAuthentications = Literal["basic", "apiKey", "bearer", None]

# String stripped of surrounding whitespace, rejected if empty afterwards
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
