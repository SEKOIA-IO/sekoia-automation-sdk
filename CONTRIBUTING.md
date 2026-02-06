# How to contribute

In order to run the test and the lint check of the project [`uv`](https://docs.astral.sh/uv/) must be installed.

## Installing dependencies

Once uv is installed, installing the project's dependencies is a matter of running the following command:

```shell
uv sync --all-extras
```

## Testing

To run the project tests simply run the following command:

```shell
uv run pytest
```

## Coding conventions

### Code formatting & linting

The Python files of the project are formatted using [Ruff](https://docs.astral.sh/ruff/).

To format the code before committing it you can run:

```shell
uv run ruff format .
```

### Code linting

To validate the code against the rules of the project [Ruff](https://docs.astral.sh/ruff/) is required.

Linting can be executed with the following command:

```shell
uv run ruff check --fix .
```

### Type checking

The project relies on [mypy](https://mypy.readthedocs.io/en/stable/) to type check python files.

Type checking can be achieved with the following command:

```shell
uv run mypy --install-types .
```

### Pre-commit hooks

Pre-commit hooks can be installed using the [pre-commit](https://pre-commit.com) tool.
Once the tool is installed the pre-commit hooks must be added to git by running the command

```shell
pre-commit install
```
