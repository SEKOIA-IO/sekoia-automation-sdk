import pytest
from pydantic import BaseModel, ValidationError

from sekoia_automation.typing import NonEmptyStr


class Arguments(BaseModel):
    value: NonEmptyStr


def test_non_empty_str_strips_whitespace():
    assert Arguments(value="  foo  ").value == "foo"


@pytest.mark.parametrize("value", ["", "   ", "\n\t"])
def test_non_empty_str_rejects_empty(value):
    with pytest.raises(ValidationError):
        Arguments(value=value)
