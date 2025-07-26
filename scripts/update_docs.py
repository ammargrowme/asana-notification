#!/usr/bin/env python3
"""Update CHANGELOG.md and README.md based on the latest commit."""
from pathlib import Path
import subprocess
import datetime


def get_latest_commit_info():
    message = subprocess.check_output(['git', 'log', '-1', '--pretty=%B']).decode().strip()
    first_line = message.splitlines()[0]
    date = subprocess.check_output(['git', 'log', '-1', '--pretty=%ad', '--date=short']).decode().strip()
    return first_line, date


def update_changelog(commit_msg, commit_date):
    path = Path('CHANGELOG.md')
    if not path.exists():
        return
    text = path.read_text().rstrip() + '\n'
    header = '## [Unreleased]'
    entry = f"- {commit_date}: {commit_msg}"
    if entry in text:
        return
    if header not in text:
        text += f"\n{header}\n"
    lines = text.splitlines()
    if header not in lines:
        lines.append(header)
    idx = lines.index(header) + 1
    lines.insert(idx, entry)
    path.write_text('\n'.join(lines) + '\n')


def update_readme(commit_msg, commit_date):
    path = Path('README.md')
    if not path.exists():
        return
    text = path.read_text().rstrip() + '\n'
    header = '## Recent Changes'
    entry = f"- {commit_date}: {commit_msg}"
    lines = text.splitlines()
    if header not in lines:
        lines.append('')
        lines.append(header)
        lines.append(entry)
    else:
        idx = lines.index(header) + 1
        if entry in lines:
            return
        lines.insert(idx, entry)
    path.write_text('\n'.join(lines) + '\n')


def main():
    commit_msg, commit_date = get_latest_commit_info()
    update_changelog(commit_msg, commit_date)
    update_readme(commit_msg, commit_date)


if __name__ == '__main__':
    main()
