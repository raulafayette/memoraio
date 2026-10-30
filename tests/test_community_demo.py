"""A public demo must seed a disposable, synthetic catalog without provider jobs."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from memoria.core import Store
from memoria.exports import locations
from scripts.community.demo import seed


class CommunityDemoTests(unittest.TestCase):
    def test_demo_catalog_is_synthetic_and_does_not_queue_provider_work(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(temp)
            with patch('socket.create_connection', side_effect=AssertionError('Fixture attempted a network connection')):
                sid = seed(store)
            with store.connect() as conn:
                sources = conn.execute('SELECT name,url FROM sources').fetchall()
                self.assertEqual(len(sources), 3)
                self.assertTrue(all('exemplo' in source['name'] and 'memoraio_fixture_' in source['url'] for source in sources))
                self.assertEqual(conn.execute('SELECT count(*) FROM transcripts WHERE current=1').fetchone()[0], 1)
                self.assertEqual(conn.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)
            exported = locations(store, sid)
            self.assertEqual(len(exported), 1)
            for record in exported.values():
                path = Path(record['path'])
                self.assertTrue(path.resolve().is_relative_to(Path(temp).resolve()))
                self.assertIn('demonstração fictícia', path.read_text())
