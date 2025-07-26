import importlib.util
import os
from unittest.mock import patch, Mock

# Import module
spec = importlib.util.spec_from_file_location(
    'asana_notification', os.path.join(os.path.dirname(__file__), '..', 'asana-notification.py')
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_fetch_commits_success():
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'sha': 'abcdef1234567890',
            'commit': {
                'author': {'name': 'Alice'},
                'message': 'Initial commit\n\nFull message'
            }
        }
    ]
    with patch('requests.get', return_value=mock_resp) as p:
        os.environ['GITHUB_REPO'] = 'owner/repo'
        commits = module.fetch_commits()
        assert commits == ['Alice: Initial commit (abcdef1)']
        p.assert_called_once()


def test_fetch_commits_failure():
    mock_resp = Mock()
    mock_resp.status_code = 500
    mock_resp.text = 'error'
    with patch('requests.get', return_value=mock_resp):
        os.environ['GITHUB_REPO'] = 'owner/repo'
        commits = module.fetch_commits()
        assert commits is None

