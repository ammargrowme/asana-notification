# Asana Notification

This repository provides a Python script and optional Docker setup for sending weekly email reports of overdue tasks from selected Asana projects. The script queries the Asana API and delivers a summary via Gmail.

## Features

- Retrieves tasks and milestones that were due before the end of the previous week.
- Looks for projects in the **Website Builds** and **Web Optimization Builds** teams, excluding specific project IDs.
- Sends a formatted HTML email showing overdue tasks grouped by project.
- Runs automatically every Monday at 08:00 MST and exposes an HTTP endpoint `/run` for manual execution.
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

The script will continue running and schedule itself every Monday. Visit `http://localhost:8080/` for a help page or `http://localhost:8080/run` to trigger it manually.

### Docker

Alternatively use Docker Compose:

```bash
docker-compose up
```

Make sure your `.env` file is in the project directory.

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

## Running Tests

Install the project dependencies and `pytest`, then execute the tests:

```bash
pip install -r requirements.txt
pip install pytest
pytest
```

## License

This project is provided as-is under the MIT License.

