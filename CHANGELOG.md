# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2025-07-25
### Changed
- Refactored email HTML generation into a dedicated `build_email_html`
  function for clearer code and stable sorting.
### Added
- Tests covering the new email HTML builder to ensure correct formatting
  and milestone inclusion.

## [1.0.0] - 2023-10-02
### Added
- Python script `asana-notification.py` for retrieving overdue Asana tasks and sending Gmail notifications.
- Dockerfile and `docker-compose.yml` for containerised execution.
- Command line options `--max-projects` and `--run-now`.
- Logging for fetching data and sending emails.
- HTTP endpoint `/run` to trigger the script manually.

## [Unreleased]
- 2025-07-25: Merge pull request #14 from ammargrowme/codex/add-commit-fetching-functionality
- 2025-07-25: Add status link on landing page
- 2025-07-25: Remove aiohttp dependency
- 2025-07-25: feat: add automatic changelog updates
