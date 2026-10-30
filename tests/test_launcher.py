"""The installed native/WSL clients discover a supervised local service."""
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest


class Launcher(unittest.TestCase):
    def test_service_publishes_private_state_and_stops_its_children(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            state = directory / 'client/ui-session.json'
            env = {**os.environ, 'MEMORIA_UI_STATE': str(state)}
            health = directory / 'data/service-health.json'
            with (directory / 'service.log').open('wb') as log:
                proc = subprocess.Popen([sys.executable, '-m', 'memoria', '--data', str(directory / 'data'), 'service', '--port', str(port)], env=env, stdout=log, stderr=log, start_new_session=True)
                connection = None
                children = []
                try:
                    deadline = time.monotonic() + 45
                    while time.monotonic() < deadline and proc.poll() is None:
                        if health.exists() and state.exists():
                            report = json.loads(health.read_text())
                            children = list(report['children'].values())
                            break
                        time.sleep(.1)
                    self.assertEqual(len(children), 8, 'Isolated local service did not become ready')
                    self.assertEqual(report['parallel_channels'], 3)
                    self.assertEqual(state.stat().st_mode & 0o777, 0o600)
                    from urllib.parse import urlsplit
                    url = urlsplit(json.loads(state.read_text())['url'])
                    self.assertEqual(url.hostname, '127.0.0.1')
                    connection = http.client.HTTPConnection(url.hostname, port, timeout=5)
                    connection.request('GET', '/?' + url.query)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 303)
                    cookie = response.getheader('Set-Cookie').split(';')[0]
                    response.read()
                    connection.request('GET', '/api/state', headers={'Cookie': cookie})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    response.read()
                    proc.terminate()
                    proc.wait(timeout=20)
                    self.assertEqual(proc.returncode, 0)
                    for pid in children:
                        with self.assertRaises(ProcessLookupError):
                            os.kill(pid, 0)
                finally:
                    if connection:
                        connection.close()
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGTERM)
                        try:
                            proc.wait(timeout=20)
                        except subprocess.TimeoutExpired:
                            os.killpg(proc.pid, signal.SIGKILL)
                            proc.wait()
