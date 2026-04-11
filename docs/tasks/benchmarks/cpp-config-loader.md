# Task

## Goal

Implement a small configuration loader for a C++ application that reads a JSON config file from disk, validates required fields, and exposes the parsed result through a simple API.

## Scope

- In scope: config model, parser/validation logic, public loader interface, and tests
- Out of scope: live config reload, environment-variable overrides, and unrelated application refactors

## Inputs

- Existing repository under the current workspace
- C++ implementation should follow the active harness guidance in `harness-cpp/`
- Config file contains fields `app_name`, `listen_port`, and `enable_metrics`

## Outputs

- Updated or new C++ source files under the relevant project directories
- Tests that exercise valid and invalid config files
- Final runtime completion summary

## Acceptance Criteria

- Valid config files load successfully and expose all required fields
- Missing required fields return structured validation failure
- Invalid port values are rejected
- Tests cover both successful parsing and representative validation errors

## Constraints

- language: cpp
- platform: windows
- harness: harness-cpp
- dependency_policy: no-new-third-party-dependencies
- forbidden_paths: docs/

## Status

ready
