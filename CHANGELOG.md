# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Triggers can retrieve module's configuration secrets by REST call to API
- Secrets can be set in Pydantic models used for generating a manifest (e.g. `api_key: str = Field(secret=True)`)
- add the ability to handle the trigger exit
- parallelize the forward of chunks of events
- Add module to create metrics in triggers

### Changed

- When updating a module's configuration, a verification is made on potentiel missing required properties

### Fixed

- Small fixes in cli commands
- Better handling of error on data path access

## [1.0.0] - 2023-02-16

### Added

- Initial release of the SDK
