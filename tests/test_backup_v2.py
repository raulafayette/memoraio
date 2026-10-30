import tempfile
import unittest
from unittest.mock import patch
from memoria.core import Store
from memoria.service import backup_if_due
class Backup(unittest.TestCase):
 def test_low_space_defers_backup_and_preserves_reserve(self):
  with tempfile.TemporaryDirectory() as d:
   store=Store(d)
   with patch('memoria.service.shutil.disk_usage',return_value=type('Disk',(),{'free':1024})()),patch.object(store,'backup') as backup:
    self.assertEqual(backup_if_due(store), 'blocked');backup.assert_not_called()
   with store.connect() as c:self.assertIsNone(c.execute("SELECT value FROM service_state WHERE key='last_backup'").fetchone())
 def test_backup_failure_does_not_terminate_service_and_retry_is_bounded(self):
  with tempfile.TemporaryDirectory() as d:
   store=Store(d)
   with patch.object(store,'backup',side_effect=OSError('Volume não disponível')) as backup:
    self.assertEqual(backup_if_due(store),'blocked');self.assertIsNone(backup_if_due(store));self.assertEqual(backup.call_count,1)
   with store.connect() as c:self.assertIn('blocked',c.execute("SELECT value FROM service_state WHERE key='backup_status'").fetchone()[0])
if __name__=='__main__':unittest.main()
