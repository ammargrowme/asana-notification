import importlib.util
import os
import json
import threading
import http.client
from http.server import HTTPServer, BaseHTTPRequestHandler

# Import the module from the script file
spec = importlib.util.spec_from_file_location(
    'asana_notification', os.path.join(os.path.dirname(__file__), '..', 'asana-notification.py')
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(module.script_progress).encode())
        else:
            self.send_response(404)
            self.end_headers()

def test_status_contains_last_run():
    server = HTTPServer(('localhost', 0), StatusHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    try:
        conn = http.client.HTTPConnection('localhost', port)
        conn.request('GET', '/status')
        response = conn.getresponse()
        data = json.loads(response.read().decode())
        assert 'last_run' in data
    finally:
        server.shutdown()
        thread.join()
