# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## 1.18.4

### Changed

- Update version of AWS libraries

## 1.18.3

### Changed

- Move to Pydantic V2 as dependency

## 1.18.2

### Changed

- Lock boto3 to versions lower than 1.36
  - The new integrity algorithm doesn't work with third party object storage implementations

### Fixed

- Fixed template for module generation

## 1.18.1 - 2024-12-04

### Added

- Add the support to list type for action response
- Add a configuration part for action documentation

### Fixed

- Fix checkpoint for timestamps

## 1.18.0 - 2024-11-26

### Changed

- Add additional values to log events sent to the API
- In Generic actions, in case of error use the message from the response if available

## 1.17.2 - 2024-11-06

### Fixed

- Fix callback URL file for account validation

## 1.17.1 - 2024-11-04

### Fixed

- Change the way to handle docker image information when publishing a module
- Fix the module synchronization script

## 1.17.0 - 2024-11-04

### Added

- Add account validation (beta)

## 1.16.1 - 2024-10-30

### Changed

- Specify docker image when publishing a module
- Move from error to info the message when no event was collected from severals seconds

### Fixed

- Replace ulrllib.parse.urljoin by posixpath.join in AsyncConnector
- Fix tests for async version of connector.
- Fix support for boolean arguments in the json_argument method

## 1.16.0 - 2024-10-16

### Changed

- Update documentation generation command to follow new structure

## 1.15.1 - 2024-10-04

### Changed

- Improve retry on some HTTP errors

## [1.15.0] - 2024-09-28

### Changed

- Make the minimal Python version to 3.10.
- Replace isort, black and autoflake with Ruff.
- Update Mypy configuration.
- Improve CI to test the package with several versions of Python.
- Update some dependencies to their latest version
  (`requests-ratelimiter`, `typer`, `prometheus-client`) and some
  devel ones (`pytest`, `pytest-asyncio`, `pytest-env`, `faker`).

## [1.14.1] - 2024-09-10

### Fixed

- For GenericAPIAction, handle when the response is a no content response
- Fix dependency issue

## [1.14.0] - 2024-08-30

### Added

- Added universal classes for a checkpoint

### Changed

- Increase number of retries and time between retries when sending requests

## [1.13.0] - 2024-04-22

### Changed

- Increase the allowed size for events to 250 kio (instead of 64 kio)

## [1.12.2] - 2024-03-26

### Fixed

- Use file for batch url computation

## [1.12.1] - 2024-03-22

### Fixed

- Fixes batch url computation

## [1.12.0] - 2024-02-27

### Added

- Limit the number of concurrent async tasks run at the same time

### Changed

- When forwarding events, use a http session to reuse the existing HTTP connection
- Improve concurrency of async tasks that forward events

## [1.11.1] - 2024-01-29

### Fixed

- Fixes connector configuration file name

## [1.11.0] - 2024-01-17

### Changed

- remove redundant logs for connectors
- Upload files by chunks to support files bigger than 100MB


## [1.10.0] - 2023-12-12

### Added

- Add heartbeat in triggers
  The heartbeat allows to mark the trigger as not alive if no heartbeat was received for a certain amount of time.
  To support this feature triggers must:
    - Set the `last_heartbeat_threshold` class attribute to a value greater than 0
    - Call periodically `self.heartbeat()` to update the last heartbeat date

## [1.9.0] - 2023-12-01

### Changed

- Thread to push logs at regular interval

### Fixed

- Remove redundant slash in URL path

## [1.8.2] - 2023-11-28

### Changed

- Improve retry for generic actions

## [1.8.1] - 2023-11-20

### Fixed

- Fix the initializer arguments for AsyncConnector

## [1.8.0] - 2023-11-13

### Added

- Add graceful delay on startup where unhandled errors won't trigger a critical exit

## [1.7.0] - 2023-11-07

### Added

- Add property to connector with `User-Agent` header to third party services
- Forward exceptions to the API

## [1.6.2] - 2023-11-06

### Fixed

- Fix json_argument fonction when url arg is empty or None

## [1.6.1] - 2023-11-06

### Fixed

- Fixes batch url computation

## [1.6.0] - 2023-10-20

### Added

- Added support for Connectors
- In script to generate new modules lock requirements

### Fixed

- In script to generate new modules fix module import for modules with spaces

## [1.5.2] - 2023-10-04

### Fixed

- Store TLS related files in a writable storage

## [1.5.1] - 2023-10-04

### Changed

- Improve error message when it is not possible to access the data storage
- Remove `chunk_size` parameter from configuration
- Try to take Intake URL from an environment var first

### Fixed

- Create volume storage if it doesn't exist before writing cert files

## [1.5.0] - 2023-09-19

### Added

- Add new wrappers to work with aio libraries such as aiohttp, aiobotocore, etc.
- New AsyncConnector that contains async implementation of push events

## [1.4.1] - 2023-09-13

### Added

- Add retry when accessing the storage

## [1.4.0] - 2023-09-09

### Added

- On critical error wait until the pod is killed instead of keep running

### Changed

- Increase time to wait without events before restarting the pod
- Send logs by batch

## [1.3.9] - 2023-08-21

### Added

- Add support for base64 encoded env variables

## [1.3.8] - 2023-07-13

### Fixed

- Fix secrets handling for triggers/connectors

## [1.3.7] - 2023-07-12

### Changed

- Retry to up to 1 hour before discarding events

## [1.3.6] - 2023-07-11

### Added

- Script to bump SDK version in all modules

### Fixed

- Fixes retry when pushing events to Sekoia.io

## [1.3.5] - 2023-06-23

### Fixed:

- Handle potential errors while handling exceptions

## [1.3.4] - 2023-06-21

### Fixed:

- Change HTTP header to check if an image exists in the registry

## [1.3.3] - 2023-06-13

### Fixed:

- In `synchronize-lib` error display docker image name used previously
- In module template don't use a specific python package index

## [1.3.2] - 2023-06-09

### Changed

- In `synchronize-lib` script:
    - Specify the registry in the image name
    - Improve checking the existence of the image in the registry

## [1.3.1] - 2023-06-08

### Changed

- In `synchronize-lib` script add support for slug based docker names
- In `synchronize-lib` script allow to use environment variable for secrets

## [1.3.0] - 2023-06-06

### Added

- Add support for TLS client authentication in S3 storage
- Launch the metrics exporter when the trigger starts
- Do not exit on critical
- Add graceful period before logging a critical error
- Add command to synchronize the module library

### Fixed

- Fix secret handling for `BaseModel` module configurations

## [1.2.0] - 2023-05-10

### Added

- Handle internal errors without increasing the error count
- Add helpers to define threads in a connector

### Fixed

- Exit infinite loop when stop event is set
- Reset error counter when pushing events to intake
- Fix logging

## [1.1.2] - 2023-04-24

### Fixed

- Fix the last event date computation used for automatic restart of connectors
- Fix threading error on shutdown

## [1.1.1] - 2023-03-28

### Fixed

- Fix setting Module configuration with Model object

## [1.1.0] - 2023-03-27

### Added

- Triggers can retrieve module's configuration secrets by REST call to API
- Secrets can be set in Pydantic models used for generating a manifest (e.g. `api_key: str = Field(secret=True)`)
- add the ability to handle the trigger exit
- parallelize the forward of chunks of events
- Add module to create metrics in triggers
- Add support for config stored inside env variables
- Add liveness HTTP endpoint to check if the trigger is still working

### Changed

- Don't retry requests to Sekoia.io with a status code of 4xx and ignore 409 errors

### Fixed

- When updating a module's configuration, a verification is made on potential missing required properties
- Specify timeout to HTTP requests


### Fixed

- Small fixes in cli commands
- Better handling of error on data path access
- Ignore tests packages to find code in the `generate-files-from-code` command
- Don't remove other menu items when generating the documentation for a single module

## [1.0.0] - 2023-02-16

### Added

- Initial release of the SDK
