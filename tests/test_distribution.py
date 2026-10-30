"""Runtime paths and WSL launcher must preserve the manual local engine."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from memoria.core import Store
from memoria.service import environment


class DistributionTests(unittest.TestCase):
    def test_service_keeps_installed_tools_in_path(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'PATH': '/custom/tools:/usr/bin'}):
            env = environment(Store(temp))
            self.assertIn('/custom/tools', env['PATH'].split(os.pathsep))
            self.assertEqual(env['MEMORIA_SERVICE'], '1')
            self.assertEqual(env['MEMORIA_DATA'], str(Path(temp).resolve()))

    def test_wsl_launcher_rejects_foreign_session_before_request(self):
        path = Path(__file__).resolve().parent.parent / 'windows/launch.py'
        spec = importlib.util.spec_from_file_location('memoraio_wsl_launcher', path)
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            (data / 'ui-session.json').write_text(json.dumps({'url': 'https://example.com/?token=test'}))
            with patch.object(launcher.urllib.request, 'urlopen') as request:
                self.assertIsNone(launcher.ready(data))
                request.assert_not_called()
