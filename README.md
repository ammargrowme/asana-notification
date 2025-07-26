# Asana Notification

This repository provides a Python script and optional Docker setup for sending weekly email reports of overdue tasks from selected Asana projects. The script queries the Asana API and delivers a summary via Gmail.

## Features

- Retrieves tasks and milestones that were due before the end of the previous week.
- Looks for projects in the **Website Builds** and **Web Optimization Builds** teams, excluding specific project IDs.
- Sends a formatted HTML email that includes a summary section and navigation links for each project.
- Runs automatically every Monday at 08:00 MST and exposes a web interface for manual execution and monitoring.
- The landing page `/` provides usage instructions, shows the last run time and lists recent GitHub commits.
- `/run` displays a live progress bar and streaming logs powered by the `/status` and `/logs` endpoints.
- Can be launched directly with Python or inside a Docker container using `docker-compose`.

## Requirements

- Python 3.8+
- Asana personal access token
- Gmail OAuth credentials (client ID, secret, refresh token and token URI)

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create an `.env` file based on `.env.example` and provide your tokens, Gmail account information and email addresses.

3. Run the script:

```bash
python asana-notification.py --run-now
```

The script will continue running and schedule itself every Monday. Visit `http://localhost:8080/` for instructions, the last run time and recent commits. Open `http://localhost:8080/run` to start a run and watch progress live. JSON data is also available at `/status` and `/logs`.

### Docker

Alternatively use Docker Compose:

```bash
docker-compose up
```

Make sure your `.env` file is in the project directory.

## Automatic Changelog Updates

Install the Git hook to keep `CHANGELOG.md` and the README's recent change
section in sync with your commits:

```bash
./hooks/install.sh
```

Every time you commit, the hook will record the commit message and date.

## Command-line Options

- `--max-projects NUM` – limit the number of projects processed.
- `--run-now` – execute the script immediately when starting.

## Environment Variables

- `ASANA_ACCESS_TOKEN` – Asana personal access token.
- `FROM_EMAIL` – address used as the sender when sending the email.
- `TO_EMAIL` – comma-separated list of recipient addresses.
- `WEB_CLIENT_ID` – Gmail OAuth client ID.
- `WEB_CLIENT_SECRET` – Gmail OAuth client secret.
- `WEB_REFRESH_TOKEN` – refresh token for OAuth.
- `WEB_TOKEN_URI` – token URI for OAuth refresh requests.
- `GITHUB_REPO` – repository in `owner/repo` form for showing recent commits.
- `GITHUB_TOKEN` – optional token for authenticated GitHub API requests.

## Running Tests

Install the project dependencies and `pytest`, then execute the tests:

```bash
pip install -r requirements.txt
pip install pytest
pytest
```

## License

This project is provided as-is under the MIT License.

## Recent Changes
- 2025-07-25: Merge pull request #24 from ammargrowme/codex/fix-progress-bar-and-status-errors
- 2025-07-25: Merge pull request #14 from ammargrowme/codex/add-commit-fetching-functionality
- 2025-07-25: Add status link on landing page
- 2025-07-25: Remove aiohttp dependency
- 2025-07-25: feat: add automatic changelog updates
