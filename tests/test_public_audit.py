"""Publication checks include attribution metadata and deleted historical files."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

AUDITOR = Path(__file__).resolve().parent.parent / 'scripts/audit_public.py'


class PublicAuditTests(unittest.TestCase):
    def repository(self, directory, email='noreply@users.noreply.github.com'):
        subprocess.run(['git', 'init', '-b', 'main', directory], check=True, capture_output=True)
        self.env = {**os.environ, 'GIT_AUTHOR_NAME': 'Example contributors', 'GIT_COMMITTER_NAME': 'Example contributors', 'GIT_AUTHOR_EMAIL': email, 'GIT_COMMITTER_EMAIL': email}

    def commit(self, directory):
        subprocess.run(['git', 'add', '.'], cwd=directory, check=True)
        subprocess.run(['git', 'commit', '-m', 'synthetic fixture'], cwd=directory, env=self.env, check=True, capture_output=True)

    def audit(self, directory):
        return subprocess.run([sys.executable, str(AUDITOR), directory, '--tracked', '--history'], capture_output=True, text=True)

    def test_rejects_personal_email_even_when_files_are_generic(self):
        with tempfile.TemporaryDirectory() as temp:
            self.repository(temp, 'person@example.invalid')
            (Path(temp) / 'README.md').write_text('Generic project')
            self.commit(temp)
            result = self.audit(temp)
            self.assertEqual(result.returncode, 1)
            self.assertIn('commit email', result.stdout)
            self.assertNotIn('person@example.invalid', result.stdout)

    def test_rejects_private_artifact_deleted_from_current_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            self.repository(temp)
            path = Path(temp) / 'data/catalog.db'
            path.parent.mkdir()
            path.write_text('synthetic fixture')
            self.commit(temp)
            path.unlink()
            (Path(temp) / 'README.md').write_text('Generic project')
            self.commit(temp)
            self.assertEqual(self.audit(temp).returncode, 1)

    def test_accepts_clean_history_and_third_party_license_attribution(self):
        with tempfile.TemporaryDirectory() as temp:
            self.repository(temp)
            (Path(temp) / 'LICENSE').write_text('Synthetic third-party notice: upstream@example.invalid')
            self.commit(temp)
            self.assertEqual(self.audit(temp).returncode, 0)
