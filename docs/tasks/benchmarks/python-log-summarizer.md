# Task

## Goal

Implement a command-line log summarizer that reads newline-delimited JSON log events from stdin and prints a compact text summary grouped by severity.

## Scope

- In scope: parser, summary aggregation, CLI entry point, and automated tests
- Out of scope: log file tailing, network ingestion, GUI output, and persistent storage

## Inputs

- Existing repo under the current workspace
- Input arrives on stdin as one JSON object per line
- Each object contains at least `level`, `message`, and `timestamp`

## Outputs

- Implementation files under a reasonable source directory for the chosen language
- Tests covering valid input and malformed input handling
- Final runtime completion summary

## Acceptance Criteria

- Valid input is grouped by severity and printed in a deterministic order
- Empty input exits successfully and prints a clear zero-event summary
- Malformed JSON produces a non-zero exit and a useful error on stderr
- New tests cover success and failure paths

## Constraints

- language: python
- platform: windows
- dependency_policy: no-new-third-party-dependencies

## Status

ready
