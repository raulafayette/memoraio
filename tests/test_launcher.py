import http.client
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import tempfile
import time
import unittest

class Launcher(unittest.TestCase):
 def test_app_bundle_starts_worker_and_shutdown_cleans_lock(self):
  with tempfile.TemporaryDirectory() as d:
   with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
   env={**os.environ,'MEMORIA_DATA':d,'BROWSER':'/usr/bin/true','MEMORIA_PORT':str(port)}
   executable=Path('Memória.app/Contents/MacOS/memoria').resolve()
   p=subprocess.Popen([str(executable)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
   connection=None
   try:
    deadline=time.monotonic()+30;url=None
    while time.monotonic()<deadline:
     log=Path(d)/'session.log'
     if log.exists():
      match=re.search(r'http://127\.0\.0\.1:(\d+)/\?token=([^\s]+)',log.read_text())
      if match:url=match;break
     if p.poll() is not None:break
     time.sleep(.1)
    self.assertIsNotNone(url,log.read_text() if log.exists() else 'No log')
    connection=http.client.HTTPConnection('127.0.0.1',int(url[1]),timeout=3)
    connection.request('GET','/?token='+url[2]);r=connection.getresponse();cookie=r.getheader('Set-Cookie').split(';')[0];r.read()
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
     connection.request('GET','/api/state',headers={'Cookie':cookie});r=connection.getresponse();state=json.loads(r.read())
     if state['worker_online']:break
     time.sleep(.1)
    self.assertTrue(state['worker_online'])
    connection.request('POST','/api/shutdown','{}',{'Cookie':cookie,'Origin':'http://127.0.0.1:'+url[1],'Content-Type':'application/json'});r=connection.getresponse();self.assertEqual(r.status,200);r.read();p.wait(timeout=5)
    self.assertFalse((Path(d)/'launcher.lock').exists());self.assertEqual(p.returncode,0)
   finally:
    if connection:connection.close()
    if p.poll() is None:
     os.killpg(p.pid,signal.SIGTERM)
     try:p.wait(timeout=10)
     except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
if __name__=='__main__':unittest.main()
