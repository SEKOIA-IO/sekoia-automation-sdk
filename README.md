# Sekoia.io Automation Python SDK

[![CI](https://github.com/SEKOIA-IO/sekoia-automation-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/SEKOIA-IO/sekoia-automation-sdk/actions/workflows/ci.yml)
[![codecov](https://codecov.io/github/SEKOIA-IO/sekoia-automation-sdk/branch/main/badge.svg?token=13S5Q0WFRQ)](https://codecov.io/github/SEKOIA-IO/sekoia-automation-sdk)
[![pypi](https://img.shields.io/pypi/v/sekoia-automation-sdk?color=%2334D058&label=pypi%20package)](https://pypi.org/project/sekoia-automation-sdk/)
[![pypi](https://img.shields.io/pypi/pyversions/sekoia-automation-sdk?color=%2334D058&label=Python)](https://pypi.org/project/sekoia-automation-sdk/)

SDK to create Sekoia.io playbook modules.

Modules can define:

* Triggers: daemons that create events that will start a playbook run
* Actions: short-lived programs that constitute the main playbook nodes. They take arguments and produce a result.

## Create a trigger

Here is how you could define a very basic trigger:

```python
from sekoia_automation.module import Module
from sekoia_automation.trigger import Trigger


class MyTrigger(Trigger):
    def run(self):
        while True:
            # Do some stuff
            self.send_event('event_name', {'somekey': 'somevalue'})
            # Maybe wait some time


if __name__ == "__main__":
    module = Module()

    module.register(MyTrigger)
    module.run()
```

You can access the Trigger's configuration with `self.configuration` and the module configuration with `self.module.configuration`.

### Attach files to an event

You can attach files to an event so that these files are available to the playbook runs.

Here is how you could crete a file that should be available to the playbook run:

```python
import os

from sekoia_automation import constants
from sekoia_automation.trigger import Trigger


class MyTrigger(Trigger):
    def run(self):
        while True:
            # Create a directory and a file
            directory_name = "test_dir"
            dirpath = os.path.join(constants.DATA_STORAGE, directory_name)
            os.makedirs(dirpath)

            with open(os.path.join(dirpath, "test.txt") "w") as f:
                f.write("Hello !")

            # Attach the file to the event
            self.send_event('event_name', {'file_path': 'test.txt'}, directory_name)

            # Maybe wait some time
```

Please note that:

* `send_event`'s third argument should be the path of a directory, relative to `constants.DATA_STORAGE`
* The directory will be the root of the playbook run's storage ("test.txt" will exist, not "test_dir/test.txt")
* You can ask the SDK to automatically remove the directory after it was copied with `remove_directory=True`
* You should always do `from sekoia_automation import constants` and use `constants.DATA_STORAGE` so that it is easy to mock

When attaching a single file to a playbook run, you can use the `write` function to create the file:

```python
from sekoia_automation.storage import write
from sekoia_automation.trigger import Trigger


class MyTrigger(Trigger):
    def run(self):
        while True:
            # Simple creation of a file
            filepath = write('test.txt', {'event': 'data'})

            # Attach the file to the event
            self.send_event('event_name', {'file_path': os.path.basename(filepath)},
                            os.path.dirname(directory_name))

            # Maybe wait some time
```

### Persisting data to disk

Most of the time, triggers have to maintain some state do to their work properly (such as a cursor).
In order to make sure that this data survives a reboot of the Trigger (which can happen with no reason),
it is useful to persist it to the trigger's storage.

When the manipulated data is JSON serializable, it is recommended to use the `PersistentJSON` class to do
so (instead of `shelve`). Used as a context manager, this class will make sure the python dict is properly
synchronised:

```python
from sekoia_automation.trigger import Trigger
from sekoia_automation.storage import PersistentJSON


class MyTrigger(Trigger):
    def run(self):
        while True:
            # Read and update state
            with PersistentJSON('cache.json') as cache:
        # Use cache as you would use a normal python dict
```

## Create an action

Here is how you could define a very basic action that simply adds its arguments as result:

```python
from sekoia_automation.module import Module
from sekoia_automation.action import Action


class MyAction(Action):
    def run(self, arguments):
        return arguments  # Return value should be a JSON serializable dict


if __name__ == "__main__":
    module = Module()

    module.register(MyAction)
    module.run()
```

There are a few more things you can do within an Action:

* Access the Module's configuration with `self.module.configuration`
* Add log messages with `self.log('message', 'level')`
* Activate an output branch with `self.set_output('malicious')` or explicitely disable another with `self.set_output('benign', False)`
* Raise an error with `self.error('error message')`. Note that raised exceptions that are not catched by your code will be automatically handled by the SDK

### Working with files

Actions can read and write files the same way a Trigger can:

```python
from sekoia_automation import constants

filepath = os.path.join(constants.DATA_STORAGE, "test.txt")
```

It is a common pattern to accept JSON arguments values directly or inside a file. The SDK provides an helper to easily read such arguments:

```python
class MyAction(Action):

    def run(self, arguments):
        test = self.json_argument("test", arguments)

        # Do somehting with test
```

The value will automatically be fetched from `test` if present, or read from the file at `test_path`.

The SDK also provides an helper to do the opposite with results:

```python
class MyAction(Action):

    def run(self, arguments):
        return self.json_result("test", {"some": "value"})
```

This will create a dict with `test_path` by default or `test` if the last argument was passed directly.

## Same Docker Image for several items

In most cases, it makes sense to define several triggers and / or actions sharing the same code and the same docker image.

In this case, here is how you should define the main:

```python
if __name__ == "__main__":
    module = Module()

    module.register(Trigger1, "command_trigger1")
    module.register(Trigger2, "command_trigger2")
    module.register(Action1, "command_action1")
    module.register(Action2, "command_action2")
    module.run()
```

The corresponding commands need to be correctly set in the manifests as "docker_parameters".

## Use with Pydantic

It is recommended to use Pydantic to develop new modules. This should ease development.

### Module Configuration

A pydantic model can be used as `self.module.configuration` by adding type hints:

```python
class MyConfigurationModel(BaseModel):
    field: str

class MyModule(Module):
    configuration: MyConfiguration

class MyAction(Action):
    module: MyModule
```

### Triggers

The Trigger configuration can also be a pydantic model by adding a type hint:

```python
class MyTrigger(Trigger):
    configuration: MyConfigurationModel
```

You can also specify the model of created events by setting the `results_model` attribute:

```python
class Event(BaseModel):
    field: str = "value"

class MyTrigger(Trigger):
    results_model = Event
```

### Actions

You can use a pydantic model as action arguments by adding a type hint:

```python
class ActionArguments(BaseModel):
    field: str = "value"

class MyAction(Action):
    def run(self, arguments: ActionArguments):
        ...
```

The model of results can also be specified by setting the `results_model` attribute:

```python
class Results(BaseModel):
    field: str = "value"

class MyAction(action):
    results_model = Results
```

### Automatically generating manifests

When using pydantic models to describe configurations, arguments and results, manifests
can be automatically generated:

```
$ poetry run sekoia-automation generate-files
```

This will do the following:

* Generate `main.py`
* Generate a manifest for each action
* Generate a manifest for each trigger
* Update the module's manifest

For better results, it is recommended to set the `name` and `description` attributes in Actions
and Triggers.
