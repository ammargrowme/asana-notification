import argparse
import requests
import datetime
import os
import base64
import json
import logging
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from oauth2client.client import OAuth2WebServerFlow
import http.server
import socketserver
from google.auth.transport.requests import Request

# Set up logging
logging.getLogger().setLevel(logging.INFO)
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.info('Starting script')

# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument('--max-projects', type=int, help='Maximum number of projects to process')
args = parser.parse_args()

# Load credentials
with open('credentials.json') as f:
    credentials_data = json.load(f)

asana_access_token = credentials_data['asana_access_token']
from_email = credentials_data['from_email']
to_email = credentials_data['to_email']

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def send_email(tasks, milestones):
    # Create the credentials object from stored credentials data
    credentials = Credentials.from_authorized_user_info(credentials_data['web'])

    if credentials.expired:
        # Refresh the access token using the refresh token
        credentials.refresh(Request())

    # Use the updated access token for API requests
    service = build('gmail', 'v1', credentials=credentials)

    projects_dict = {}

    # Organize tasks by projects
    for task_name, task_due_date, assignee_name, task_url, project_name in tasks:
        if project_name not in projects_dict:
            projects_dict[project_name] = []
        projects_dict[project_name].append((task_name, task_due_date, assignee_name, task_url))

    # Organize milestones by projects
    for milestone_name, milestone_due_date, assignee_name, milestone_url, project_name in milestones:
        if project_name not in projects_dict:
            projects_dict[project_name] = []
        projects_dict[project_name].append((milestone_name, milestone_due_date, assignee_name, milestone_url))

    # Sort projects_dict based on the total number of tasks and milestones combined
    sorted_projects = sorted(projects_dict.items(), key=lambda x: len(x[1]), reverse=True)

    message_text = ''

    for project_name, project_items in sorted_projects:
        if len(project_items) == 0:
            continue  # Skip empty projects

        project_tasks = [item for item in project_items if len(item) == 4]  # Filter out milestones
        project_milestones = [item for item in project_items if len(item) == 5]  # Filter out tasks

        if len(project_tasks) == 0 and len(project_milestones) == 0:
            continue  # Skip projects without tasks or milestones

        tasks_table = f'<h1>{project_name} Tasks</h1>'
        tasks_table += '''
        <table style="border:1px solid black; border-collapse:collapse; width:100%;">
            <tr>
                <th style="text-align:center; font-weight:bold; border:1px solid black;">Task Name</th>
                <th style="text-align:center; font-weight:bold; border:1px solid black;">Due Date</th>
                <th style="text-align:center; font-weight:bold; border:1px solid black;">Assignee</th>
            </tr>'''
        for task_name, task_due_date, assignee_name, task_url in project_tasks:
            tasks_table += f'''
            <tr>
                <td style="border:1px solid black;"><a href="{task_url}">{task_name}</a></td>
                <td style="border:1px solid black;">{task_due_date}</td>
                <td style="border:1px solid black;">{assignee_name}</td>
            </tr>'''
        tasks_table += '</table>'

        if project_milestones:
            milestones_table = f'<h1>{project_name} Milestones</h1>'
            milestones_table += '''
            <table style="border:1px solid black; border-collapse:collapse; width:100%;">
                <tr>
                    <th style="text-align:center; font-weight:bold; border:1px solid black;">Milestone Name</th>
                    <th style="text-align:center; font-weight:bold; border:1px solid black;">Due Date</th>
                    <th style="text-align:center; font-weight:bold; border:1px solid black;">Assignee</th>
                </tr>'''
            for milestone_name, milestone_due_date, assignee_name, milestone_url in project_milestones:
                milestones_table += f'''
                <tr>
                    <td style="border:1px solid black;"><a href="{milestone_url}">{milestone_name}</a></td>
                    <td style="border:1px solid black;">{milestone_due_date}</td>
                    <td style="border:1px solid black;">{assignee_name}</td>
                </tr>'''
            milestones_table += '</table>'

            message_text += f'{milestones_table}{tasks_table}'
        else:
            message_text += tasks_table

    if not message_text:
        message_text = '<p>No overdue tasks or milestones found.</p>'

    message = MIMEText(message_text, 'html')  # Set the second parameter to 'html'
    message['to'] = to_email
    message['from'] = from_email
    message['subject'] = 'Overdue Asana Tasks'
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service.users().messages().send(userId='me', body={'raw': raw_message}).execute()


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

# Get un-archived projects in the organization
projects = []
offset = None
while True:
    params = {'limit': 100, 'workspace': workspace_id, 'archived': False}
    if offset is not None:
        params['offset'] = offset
    response = requests.get(
        'https://app.asana.com/api/1.0/projects',
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

# Calculate the start and end of last week
today = datetime.datetime.now().date()
start_of_week = today - datetime.timedelta(days=today.weekday())
last_week_start = start_of_week - datetime.timedelta(days=7)
last_week_end = start_of_week - datetime.timedelta(days=1)

# For each project, get all incomplete tasks that are due before now
total_projects = len(projects)
projects_processed = 0

max_projects = args.max_projects if args.max_projects is not None else total_projects

for project in projects[:max_projects]:
    offset = None
    while True:
        params = {
            'completed': False,
            'due_on.before': last_week_end.isoformat(),
            'due_on.after': last_week_start.isoformat(),
            'project': project['gid'],
            'limit': 100,
            'opt_fields': 'name,due_on,assignee,assignee.name,permalink_url,resource_subtype, completed, completed_at'  # Request additional fields
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
            print(f"Project details: {project_tasks}")
            for task in project_tasks:
                task_name = task.get('name')
                task_due_date = task.get('due_on')
                assignee = task.get('assignee')
                assignee_name = assignee.get('name') if assignee is not None else None
                task_url = task.get('permalink_url')
                completed = task.get('completed')
                completed_at = task.get('completed_at')
                project_name = project['name']  # Get the project name

                if task_due_date is None or assignee_name is None or completed or completed_at is not None:
                    print(f"Skipping task: {task_name} - Due Date: {task_due_date} - Assignee: {assignee_name} - Completed: {completed} - Completed At: {completed_at}")
                    continue  # Skip tasks without a due date, assignee, or completed tasks

                if task.get('resource_subtype') == 'milestone':
                    milestones.append((task_name, task_due_date, assignee_name, task_url, project_name))  # Include project name
                    print(f"Added milestone: {task_name} - Due Date: {task_due_date} - Assignee: {assignee_name} - Completed: {completed} - Completed At: {completed_at}")
                else:
                    tasks.append((task_name, task_due_date, assignee_name, task_url, project_name))  # Include project name
                    print(f"Added task: {task_name} - Due Date: {task_due_date} - Assignee: {assignee_name} - Completed: {completed} - Completed At: {completed_at}")


            next_page = response.json().get('next_page')
            if next_page is not None:
                offset = next_page.get('offset')
            else:
                break
        else:
            logging.error('Failed to fetch tasks for project %s: %s %s', project['gid'], response.status_code, response.text)
            break

    projects_processed += 1

    logging.info('Projects Processed: %d/%d', projects_processed, max_projects)
    logging.info('---')

# Send an email with the overdue tasks and milestones
logging.info('Sending email')
send_email(tasks, milestones)

logging.info('Script completed')
