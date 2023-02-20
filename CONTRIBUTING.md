# How to contribute

In order to run the test and the lint check of the project [Poetry](https://python-poetry.org/) must be installed. 

## Installing dependencies

Once poetry is installing the dependencies of the project is a matter of running the following command:

```shell
poetry install
```

## Testing

To run the project tests simply run the following command:

```shell
poetry run pytest
```

## Coding conventions

### Code formatting

The python files of the project are formatted using [Black](https://black.readthedocs.io/).

To format the code before committing it you can run:

```shell
poetry run black .
```

### Code linting

To validate the code against the rules of the project [Ruff](https://beta.ruff.rs/docs/) is required.

Linting can be executed with the following command:

```shell
poetry run ruff --fix .
```

### Type checking

The project relies on [mypy](https://mypy.readthedocs.io/en/stable/) to type check python files.

Type checking can be achieved with the following command:

```shell
poetry run mypy --install-types .
```

### Pre-commit hooks

Pre-commit hooks can be installed using the [pre-commit](https://pre-commit.com) tool. 
Once the tool is installed the pre-commit hooks must be added to git by running the command

```shell
pre-commit install
```

