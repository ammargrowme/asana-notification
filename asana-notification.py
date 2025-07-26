import argparse
import requests
import datetime
import os
import base64
import logging
import sys
import threading
import schedule
import time
import json
import google.auth.exceptions
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from http.server import HTTPServer, BaseHTTPRequestHandler
from google.auth.transport.requests import Request

# Set up logging
logging.getLogger().setLevel(logging.INFO)
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info('Starting script')

# Keep recent log messages in memory for the web UI
log_buffer = []


class InMemoryLogHandler(logging.Handler):
    """Custom logging handler storing log messages in a buffer."""

    def emit(self, record):
        log_entry = self.format(record)
        log_buffer.append(log_entry)
        # Limit buffer size to last 100 entries
        if len(log_buffer) > 100:
            del log_buffer[0]


# Attach handler to root logger
memory_handler = InMemoryLogHandler()
memory_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(memory_handler)

# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument('--max-projects', type=int, help='Maximum number of projects to process')
parser.add_argument('--run-now', action='store_true', help='Run the script immediately')
args = None

# Get environment variables. Using `get` prevents import errors during testing
asana_access_token = os.environ.get('ASANA_ACCESS_TOKEN')
from_email = os.environ.get('FROM_EMAIL')
to_emails = os.environ.get('TO_EMAIL', '').split(',')

# Define list of excluded projects
excluded_projects = ['310779989024082', '1111864722010765', '1204430533460894']

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Track progress information for the web UI
script_progress = {
    'total_projects': 0,
    'processed_projects': 0,
    'running': False,
    'complete': False,
    'last_run': None,
}


def fetch_commits():
    """Retrieve recent commits from the configured GitHub repository."""
    repo = os.environ.get("GITHUB_REPO")
    token = os.environ.get("GITHUB_TOKEN")

    if not repo:
        return []

    url = f"https://api.github.com/repos/{repo}/commits"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        response = requests.get(url, params={"per_page": 5}, headers=headers, timeout=10)
    except requests.RequestException as exc:
        logging.error("Error fetching commits: %s", exc)
        return None

    if response.status_code != 200:
        logging.error("Failed to fetch commits: %s %s", response.status_code, response.text)
        return None

    commits = []
    for entry in response.json():
        author = entry.get("commit", {}).get("author", {}).get("name", "Unknown")
        message = entry.get("commit", {}).get("message", "").splitlines()[0]
        sha = entry.get("sha", "")[:7]
        commits.append(f"{author}: {message} ({sha})")

    return commits

def build_email_html(tasks, milestones):
    """Create the HTML body for the email."""
    projects_dict = {}

    # Organize tasks and milestones by projects
    for task_name, task_due_date, assignee_name, task_url, project_name in tasks + milestones:
        if project_name not in projects_dict:
            projects_dict[project_name] = []
        item_type = 'Milestone' if (task_name, task_due_date, assignee_name, task_url, project_name) in milestones else 'Task'
        projects_dict[project_name].append((item_type, task_name, task_due_date, assignee_name, task_url))

    # Sort projects alphabetically for stable output
    sorted_projects = sorted(projects_dict.items(), key=lambda x: x[0])

    summary = {}
    for project_name, project_items in projects_dict.items():
        task_count = sum(1 for i in project_items if i[0] == 'Task')
        milestone_count = sum(1 for i in project_items if i[0] == 'Milestone')
        summary[project_name] = (task_count, milestone_count)

    message_text = (
        '<div style="font-family:Arial, sans-serif; color:#000000; background-color:#ffffff;">'
        '<style>'
        'table{border-collapse:collapse;width:100%;max-width:600px;}'
        'th,td{padding:8px;border:1px solid #cccccc;text-align:left;}'
        'th{background-color:#f0f0f0;}'
        'tbody tr:nth-child(even){background-color:#f9f9f9;}'
        '</style>'
    )

    if summary:
        message_text += '<h1>Summary</h1><ul>'
        for name in sorted(summary.keys()):
            tasks_total, milestones_total = summary[name]
            total = tasks_total + milestones_total
            message_text += f'<li>{name}: {total} overdue ({tasks_total} tasks, {milestones_total} milestones)</li>'
        message_text += '</ul>'

    # Add table of contents linking to each project
    if sorted_projects:
        message_text += '<h1>Table of Contents</h1><ul>'
        for project_name, _ in sorted_projects:
            anchor = project_name.lower().replace(" ", "-")
            message_text += f'<li><a href="#{anchor}">{project_name}</a></li>'
        message_text += '</ul>'

    for project_name, project_items in sorted_projects:
        if len(project_items) == 0:
            continue  # Skip projects without tasks or milestones

        anchor = project_name.lower().replace(' ', '-')
        tasks_table = f'<a name="{anchor}"></a><h1>{project_name} Tasks</h1>'
        tasks_table += '''
        <table style="border:1px solid #cccccc; border-collapse:collapse; width:100%; max-width:600px;">
            <tr>
                <th style="text-align:left !important; font-weight:bold; border:1px solid #cccccc; padding:8px; background-color:#f0f0f0;">Type</th>
                <th style="text-align:left !important; font-weight:bold; border:1px solid #cccccc; padding:8px; background-color:#f0f0f0;">Task Name</th>
                <th style="text-align:left !important; font-weight:bold; border:1px solid #cccccc; padding:8px; background-color:#f0f0f0;">Due Date</th>
                <th style="text-align:left !important; font-weight:bold; border:1px solid #cccccc; padding:8px; background-color:#f0f0f0;">Days Overdue</th>
                <th style="text-align:left !important; font-weight:bold; border:1px solid #cccccc; padding:8px; background-color:#f0f0f0;">Assignee</th>
            </tr>'''

        # Sort each project's items by due date
        for item_type, task_name, task_due_date, assignee_name, task_url in sorted(project_items, key=lambda x: x[2]):
            days_overdue = (datetime.date.today() - task_due_date).days
            row_color = '#ffffff'
            if days_overdue > 14:
                row_color = '#f8d7da'
            elif days_overdue > 7:
                row_color = '#fff3cd'
            tasks_table += f'''
            <tr style="background-color:{row_color};">
                <td style="border:1px solid #cccccc; padding:8px;">{item_type}</td>
                <td style="border:1px solid #cccccc; padding:8px;"><a href="{task_url}">{task_name}</a></td>
                <td style="border:1px solid #cccccc; padding:8px;">{task_due_date.strftime("%Y-%m-%d")}</td>
                <td style="border:1px solid #cccccc; padding:8px;">{days_overdue}</td>
                <td style="border:1px solid #cccccc; padding:8px;">{assignee_name}</td>
            </tr>'''

        tasks_table += '</table>'

        message_text += tasks_table

    if message_text == '<div style="font-family:Arial, sans-serif; color:#000000; background-color:#ffffff;">':
        message_text += '<p>No overdue tasks or milestones found.</p>'

    message_text += '<hr/><p><a href="http://localhost:8080/run">View online</a></p>'
    message_text += '<p style="font-size:12px;color:#666;">Automated Asana report</p>'
    message_text += '</div>'

    return message_text


def send_email(tasks, milestones):
    # Create the credentials object from environment variables
    credentials = Credentials.from_authorized_user_info({
        'client_id': os.environ['WEB_CLIENT_ID'],
        'client_secret': os.environ['WEB_CLIENT_SECRET'],
        'refresh_token': os.environ.get('WEB_REFRESH_TOKEN'),
        'token_uri': os.environ['WEB_TOKEN_URI'],
    })

    try:
        if credentials.expired:
            credentials.refresh(Request())
    except google.auth.exceptions.RefreshError:
        logging.error('Token has been expired or revoked. Please re-authenticate.')
        return
    # Use the updated access token for API requests
    service = build('gmail', 'v1', credentials=credentials)

    message_text = build_email_html(tasks, milestones)

    message = MIMEText(message_text, 'html')  # Set the second parameter to 'html'
    message['to'] = ', '.join(to_emails)
    message['from'] = from_email
    message['subject'] = 'Overdue Asana Tasks and Milestones'
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()



    service.users().messages().send(userId='me', body={'raw': raw_message}).execute()



def run_script():
    global script_progress
    script_progress['running'] = True
    script_progress['complete'] = False
    script_progress['processed_projects'] = 0
    # Get workspace ID
    logging.info('Fetching workspace ID')
    response = requests.get(
        'https://app.asana.com/api/1.0/workspaces',
        headers={'Authorization': 'Bearer ' + asana_access_token},
    )

    if response.status_code == 200:
        workspace_id = response.json()['data'][0]['gid']
        logging.info('Workspace ID: %s', workspace_id)
    else:
        logging.error('Failed to fetch workspaces: %s %s', response.status_code, response.text)
        workspace_id = None

    # Fetch teams
    logging.info('Fetching teams')
    response = requests.get(
        f'https://app.asana.com/api/1.0/workspaces/{workspace_id}/teams',
        headers={'Authorization': 'Bearer ' + asana_access_token},
    )

    if response.status_code == 200:
        teams = response.json()['data']
        desired_teams = ["Website Builds", "Web Optimization Builds"]
        team_ids = [team['gid'] for team in teams if team['name'] in desired_teams]
        logging.info('Teams fetched successfully')
        logging.info('Teams ID: %s', team_ids)

    else:
        logging.error('Failed to fetch teams: %s %s', response.status_code, response.text)
        team_ids = []

    # Get un-archived projects for the specified teams
    projects = []
    for team_id in team_ids:
        offset = None
        while True:
            params = {
                'limit': 100,
                'team': team_id,
                'archived': False
            }
            if offset is not None:
                params['offset'] = offset
            response = requests.get(
                f'https://app.asana.com/api/1.0/teams/{team_id}/projects',
                headers={'Authorization': 'Bearer ' + asana_access_token},
                params=params
            )

            if response.status_code == 200:
                data = response.json()['data']
                projects.extend(data)
                next_page = response.json().get('next_page')
                if next_page is not None:
                    offset = next_page.get('offset')
                else:
                    break
            else:
                logging.error('Failed to fetch projects: %s %s', response.status_code, response.text)
                break



    tasks = []
    milestones = []

    # Calculate the end of last week
    # Considering the MST timezone which is UTC-7
    today = datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(hours=7)
    start_of_week = today - datetime.timedelta(days=today.weekday())
    last_week_end = start_of_week - datetime.timedelta(days=1)

    # For each project, get all incomplete tasks that are due before now
    total_projects = len(projects)
    projects_processed = 0

    max_projects = args.max_projects if args.max_projects is not None else total_projects
    script_progress['total_projects'] = max_projects

    for project in projects[:max_projects]:
        if project['gid'] in excluded_projects:
            logging.info(f'Skipping excluded project with ID {project["gid"]}')
            continue
        offset = None
        while True:
            params = {
                'completed_since': 'now',  # Fetch only tasks that are not completed
                'due_on.before': last_week_end.isoformat(),  # Fetch tasks due before the end of last week
                'project': project['gid'],
                'limit': 100,
                'opt_fields': 'name,due_on,assignee,assignee.name,permalink_url,resource_subtype'
            }
            
            if offset is not None:
                params['offset'] = offset
            response = requests.get(
                'https://app.asana.com/api/1.0/tasks',
                headers={'Authorization': 'Bearer ' + asana_access_token},
                params=params
            )

            if response.status_code == 200:
                project_tasks = response.json()['data']
                logging.debug("Project details: %s", project_tasks)
                for task in project_tasks:
                    task_name = task.get('name')
                    task_due_date = task.get('due_on')
                    assignee = task.get('assignee')
                    assignee_name = assignee.get('name') if assignee is not None else None
                    task_url = task.get('permalink_url')
                    completed = task.get('completed')
                    completed_at = task.get('completed_at')
                    project_name = project['name']  

                    if task_due_date is None or assignee_name is None or completed:
                        logging.debug("Skipping task: %s - Due Date: %s - Assignee: %s - Completed: %s - Completed At: %s", task_name, task_due_date, assignee_name, completed, completed_at)
                        continue  # Skip tasks without a due date, assignee, or completed tasks

                    # Check if the task's due date is after the end of last week
                    task_due_date_dt = datetime.datetime.fromisoformat(task_due_date)
                    if task_due_date_dt.date() > last_week_end:
                        logging.debug("Skipping task: %s - Due Date: %s - Assignee: %s - Completed: %s - Completed At: %s", task_name, task_due_date, assignee_name, completed, completed_at)
                        continue

                    if task.get('resource_subtype') == 'milestone':
                        milestones.append((task_name, task_due_date_dt.date(), assignee_name, task_url, project_name)) 
                        logging.debug("Added milestone: %s - Due Date: %s - Assignee: %s - Completed: %s - Completed At: %s", task_name, task_due_date, assignee_name, completed, completed_at)
                    else:
                        tasks.append((task_name, task_due_date_dt.date(), assignee_name, task_url, project_name))
                        logging.debug("Added task: %s - Due Date: %s - Assignee: %s - Completed: %s - Completed At: %s", task_name, task_due_date, assignee_name, completed, completed_at)

                next_page = response.json().get('next_page')
                if next_page is not None:
                    offset = next_page.get('offset')
                else:
                    break
            else:
                logging.error('Failed to fetch tasks for project %s: %s %s', project['gid'], response.status_code, response.text)
                break

        projects_processed += 1
        script_progress['processed_projects'] = projects_processed

        logging.info('Projects Processed: %d/%d', projects_processed, max_projects)
        logging.info('---')


    # Send an email with the overdue tasks and milestones
    logging.info('Sending email')
    send_email(tasks, milestones)

    logging.info('Script completed')
    script_progress['running'] = False
    script_progress['complete'] = True
    script_progress['last_run'] = datetime.datetime.utcnow().isoformat()

def serve_http(port=8080, bind=""):
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ('/', '/index.html'):
                commits = fetch_commits()
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                if commits is None:
                    commits_html = '<p>Unable to load commits</p>'
                elif commits:
                    commits_html = '<ul>' + ''.join(f'<li>{c}</li>' for c in commits) + '</ul>'
                else:
                    commits_html = ''
                html = f"""
                <!DOCTYPE html>
                <html lang='en'>
                <head>
                <meta charset='utf-8'/>
                <meta name='viewport' content='width=device-width, initial-scale=1'/>
                <title>Asana Notification</title>
                <style>
                body {{ font-family: Arial, sans-serif; margin:0; padding:20px; background:#f7f7f7; }}
                .container {{ max-width:800px; margin:auto; background:#fff; padding:20px; box-shadow:0 2px 4px rgba(0,0,0,0.1); }}
                pre {{ background:#f0f0f0; padding:10px; overflow:auto; }}
                @media (max-width:600px) {{ body {{ padding:10px; }} }}
                </style>
                </head>
                <body>
                <div class='container'>
                <h1>Asana Notification</h1>
                <p>This application collects overdue Asana tasks and emails a weekly summary.</p>
                <p>To trigger a run manually, open <strong><a href='/run'>/run</a></strong> in your browser.</p>
                <h2>Manual Execution</h2>
                <p>Prepare a <code>.env</code> file using <code>.env.example</code> and then run:</p>
                <pre>python asana-notification.py --run-now</pre>
                <p>You may also start it with Docker:</p>
                <pre>docker-compose up</pre>
                <h2>Recent Commits</h2>
                {commits_html}
                <p>Last run: {script_progress['last_run'] or 'Never'}</p>
                </div>
                </body>
                </html>
                """
                self.wfile.write(html.encode())
            elif self.path == '/run':
                logging.info("Received HTTP request to run script")
                if not script_progress['running']:
                    threading.Thread(target=run_script, daemon=True).start()
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                html = """
                <html><head><title>Asana Notification</title>
                <style>
                body { font-family: Arial, sans-serif; margin: 2em; background-color: #f4f4f4; }
                .container { max-width: 800px; margin: auto; background: #fff; padding: 1em; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
                #progress-container { width: 100%; background-color: #ddd; border-radius: 5px; overflow: hidden; }
                #progress-bar { width: 0%; height: 30px; background-color: #4caf50; text-align: center; line-height: 30px; color: white; }
                #logs { background:#000; color:#0f0; padding:0.5em; height:200px; overflow-y:scroll; font-family: monospace; }
                </style>
                <script>
                function update() {
                  fetch('/status').then(r => r.json()).then(data => {
                    var percent = 0;
                    if (data.total_projects > 0) {
                      percent = Math.round((data.processed_projects / data.total_projects) * 100);
                    }
                    document.getElementById('progress-bar').style.width = percent + '%';
                    document.getElementById('progress-bar').textContent = percent + '%';
                    document.getElementById('details').textContent = data.processed_projects + ' / ' + data.total_projects + ' projects';
                    var status = 'Running...';
                    if (!data.running) {
                      status = data.complete ? 'Completed' : 'Idle';
                    }
                    document.getElementById('status').textContent = status;
                    document.getElementById('last_run').textContent = data.last_run || 'Never';
                  });
                  fetch('/logs').then(r => r.json()).then(data => {
                    document.getElementById('logs').textContent = data.logs.join('\n');
                    var logEl = document.getElementById('logs');
                    logEl.scrollTop = logEl.scrollHeight;
                  });
                }
                setInterval(update, 2000);
                window.onload = update;
                </script></head>
                <body>
                <div class='container'>
                <h1>Asana Notification</h1>
                <div id='progress-container'><div id='progress-bar'>0%</div></div>
                <p id='details'></p>
                <p>Status: <span id='status'>Starting...</span></p>
                <p>Last run: <span id='last_run'>{script_progress['last_run'] or 'Never'}</span></p>
                <h2>Logs</h2>
                <pre id='logs'></pre>
                </div>
                </body></html>
                """
                self.wfile.write(html.encode())
            elif self.path == '/status':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(script_progress).encode())
            elif self.path == '/logs':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'logs': log_buffer}).encode())
            else:
                self.send_response(404)
                self.end_headers()

    httpd = HTTPServer((bind, port), RequestHandler)
    logging.info(f"Starting HTTP server on {bind}:{port}")
    httpd.serve_forever()

def main():
    """Entry point for running the scheduler and HTTP server."""
    global args
    args = parser.parse_args()
    # Schedule the script to run every Monday at 8 AM MST
    logging.info('---')
    logging.info('Running weekly script')
    logging.info('---')
    schedule.every().monday.at("08:00").do(run_script)

    # If the --run-now argument is specified, run the script immediately
    if args.run_now:
        logging.info('---')
        logging.info('Running manually.')
        run_script()
        logging.info('---')
        logging.info('Finished running script manually. Waiting for run command or weekly run.')

    # Start HTTP server in a separate thread
    http_thread = threading.Thread(target=serve_http)
    http_thread.start()

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
