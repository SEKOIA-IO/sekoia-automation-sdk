# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## Changed

- Thread to push logs at regular interval

## [1.8.3] - 2023-12-01

## Fixed

- Remove redundant slash in URL path

## [1.8.2] - 2023-11-28

## Changed

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
