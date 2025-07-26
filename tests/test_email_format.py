import datetime
import importlib.util
import os

# Import the module from the script file
spec = importlib.util.spec_from_file_location(
    'asana_notification', os.path.join(os.path.dirname(__file__), '..', 'asana-notification.py')
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_build_email_html_simple():
    tasks = [(
        'Task1',
        datetime.date(2023, 9, 10),
        'Alice',
        'http://example.com/1',
        'Project A'
    )]
    milestones = []
    html = module.build_email_html(tasks, milestones)
    assert 'Task1' in html
    assert 'Project A' in html
    assert '<table' in html


def test_tasks_sorted_by_due_date():
    tasks = [
        (
            'Task later',
            datetime.date(2023, 9, 20),
            'Bob',
            'http://example.com/2',
            'Project B',
        ),
        (
            'Task sooner',
            datetime.date(2023, 9, 10),
            'Bob',
            'http://example.com/3',
            'Project B',
        ),
    ]
    milestones = []
    html = module.build_email_html(tasks, milestones)
    first_idx = html.find('Task sooner')
    second_idx = html.find('Task later')
    assert first_idx < second_idx


def test_milestones_and_tasks_included():
    tasks = [
        (
            'Task1',
            datetime.date(2023, 9, 10),
            'Alice',
            'http://example.com/1',
            'Project C',
        )
    ]
    milestones = [
        (
            'Milestone1',
            datetime.date(2023, 9, 5),
            'Alice',
            'http://example.com/m1',
            'Project C',
        )
    ]
    html = module.build_email_html(tasks, milestones)
    assert 'Milestone1' in html
    assert 'Task1' in html


def test_projects_sorted_alphabetically():
    tasks = [
        (
            'Task B',
            datetime.date(2023, 9, 10),
            'Alice',
            'http://example.com/b',
            'Project B',
        ),
        (
            'Task A',
            datetime.date(2023, 9, 10),
            'Alice',
            'http://example.com/a',
            'Project A',
        ),
        (
            'Task C',
            datetime.date(2023, 9, 10),
            'Alice',
            'http://example.com/c',
            'Project C',
        ),
    ]
    milestones = []
    html = module.build_email_html(tasks, milestones)
    idx_a = html.find('<h1>Project A Tasks</h1>')
    idx_b = html.find('<h1>Project B Tasks</h1>')
    idx_c = html.find('<h1>Project C Tasks</h1>')
    assert idx_a < idx_b < idx_c

