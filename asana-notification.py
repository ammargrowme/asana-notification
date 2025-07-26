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
}

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

    message_text = ''

    for project_name, project_items in sorted_projects:
        if len(project_items) == 0:
            continue  # Skip projects without tasks or milestones

        tasks_table = f'<h1>{project_name} Tasks</h1>'
        tasks_table += '''
        <table style="border:1px solid black; border-collapse:collapse; width:100%;">
            <tr>
                <th style="text-align:left !important; font-weight:bold; border:1px solid black;">Type</th>
                <th style="text-align:left !important; font-weight:bold; border:1px solid black;">Task Name</th>
                <th style="text-align:left !important; font-weight:bold; border:1px solid black;">Due Date</th>
                <th style="text-align:left !important; font-weight:bold; border:1px solid black;">Assignee</th>
            </tr>'''

        # Sort each project's items by due date
        for item_type, task_name, task_due_date, assignee_name, task_url in sorted(project_items, key=lambda x: x[2]):
            tasks_table += f'''
            <tr>
                <td style="border:1px solid black;">{item_type}</td>
                <td style="border:1px solid black;"><a href="{task_url}">{task_name}</a></td>
                <td style="border:1px solid black;">{task_due_date.strftime("%Y-%m-%d")}</td>
                <td style="border:1px solid black;">{assignee_name}</td>
            </tr>'''

        tasks_table += '</table>'

        message_text += tasks_table

    if not message_text:
        message_text = '<p>No overdue tasks or milestones found.</p>'

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

def serve_http(port=8080, bind=""):
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/run':
                logging.info("Received HTTP request to run script")
                if not script_progress['running']:
                    threading.Thread(target=run_script, daemon=True).start()
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                html = """
                <html><head><title>Script Progress</title>
                <style>
                body { font-family: Arial, sans-serif; margin: 2em; }
                #progress-container { width: 100%; background-color: #ddd; border-radius: 5px; }
                #progress-bar { width: 0%; height: 30px; background-color: #4caf50; text-align: center; line-height: 30px; color: white; border-radius: 5px; }
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
                    var status = 'Running...';
                    if (!data.running) {
                      status = data.complete ? 'Completed' : 'Idle';
                    }
                    document.getElementById('status').textContent = status;
                  });
                }
                setInterval(update, 2000);
                window.onload = update;
                </script></head>
                <body>
                <h1>Asana Notification</h1>
                <div id='progress-container'><div id='progress-bar'>0%</div></div>
                <p id='status'>Starting...</p>
                </body></html>
                """
                self.wfile.write(html.encode())
            elif self.path == '/status':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(script_progress).encode())
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
