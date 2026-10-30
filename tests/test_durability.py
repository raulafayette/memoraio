import errno
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from memoria.core import atomic_json

class Durability(unittest.TestCase):
 def test_enospc_preserves_previous_file(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'metadata.json';atomic_json(path,{'version':1})
   with patch('memoria.core.os.replace',side_effect=OSError(errno.ENOSPC,'disk full')):
    with self.assertRaises(OSError):atomic_json(path,{'version':2})
   self.assertEqual(json.loads(path.read_text()),{'version':1})
 def test_child_keeps_staging_lock_after_worker_is_killed(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);marker=root/'child.pid';lock_path=root/'staging.lock'
   code='''
import os,sys,fcntl
from pathlib import Path
from memoria.core import Store
from memoria.worker import Worker
root=Path(sys.argv[1]);s=Store(root/'data');s.add_source('https://youtu.be/BaW_jenozKc');w=Worker(s,reserve=0);j=s.claim(w.owner)
lock=open(root/'staging.lock','a');fcntl.flock(lock,fcntl.LOCK_EX);w.lock_fd=lock.fileno()
child="import os,time; from pathlib import Path; Path("+repr(str(root/'child.pid'))+").write_text(str(os.getpid())); time.sleep(60)"
w.run_command([sys.executable,'-c',child],j)
'''
   parent=subprocess.Popen([sys.executable,'-c',code,str(root)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   child_pid=None
   try:
    deadline=time.monotonic()+5
    while not marker.exists() and time.monotonic()<deadline:time.sleep(.05)
    self.assertTrue(marker.exists());child_pid=int(marker.read_text());parent.kill();parent.wait()
    with open(lock_path,'a') as f:
     with self.assertRaises(BlockingIOError):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    os.killpg(child_pid,signal.SIGTERM);child_pid=None
   finally:
    if parent.poll() is None:parent.kill();parent.wait()
    if child_pid:
     try:os.killpg(child_pid,signal.SIGKILL)
     except ProcessLookupError:pass
if __name__=='__main__':unittest.main()

class ConcurrentPublication(unittest.TestCase):
 def test_concurrent_atomic_writes_are_complete_and_leave_no_partial_files(self):
  import concurrent.futures
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'shared.json'
   def write(i):atomic_json(path,{'writer':i,'payload':str(i)*10000})
   with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(write,range(24)))
   doc=json.loads(path.read_text());self.assertEqual(doc['payload'],str(doc['writer'])*10000)
   self.assertEqual(list(Path(d).glob('*.tmp')),[])
 def test_strong_sqlite_flush_is_enabled(self):
  from memoria.core import Store
  with tempfile.TemporaryDirectory() as d:
   s=Store(d)
   with s.connect() as c:self.assertEqual(c.execute('PRAGMA synchronous').fetchone()[0],2);self.assertEqual(c.execute('PRAGMA fullfsync').fetchone()[0],1)
