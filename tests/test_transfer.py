"""Real yt-dlp transfer against an isolated, controlled local HTTP fixture."""
import http.server
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest
from memoria.core import Store,Failure
from memoria.worker import Worker

class Transfer(unittest.TestCase):
 def test_connection_drop_partial_and_resume(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);fixture=root/'fixture.mp4'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=64x64:d=0.2','-c:v','libx264','-y',str(fixture)],check=True)
   payload=fixture.read_bytes()+os.urandom(512*1024)
   state={'drop':True,'ranges':[]}
   class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_HEAD(self):
     self.send_response(200);self.send_header('Content-Type','video/mp4');self.send_header('Content-Length',str(len(payload)));self.send_header('Accept-Ranges','bytes');self.end_headers()
    def do_GET(self):
     value=self.headers.get('Range');start=int(value.split('=')[1].split('-')[0]) if value else 0
     if value:state['ranges'].append(start)
     self.send_response(206 if value else 200);self.send_header('Content-Type','video/mp4');self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(len(payload)-start))
     if value:self.send_header('Content-Range',f'bytes {start}-{len(payload)-1}/{len(payload)}')
     self.end_headers()
     if state['drop']:
      self.wfile.write(payload[start:start+65536]);self.wfile.flush();self.connection.shutdown(socket.SHUT_RDWR);self.connection.close()
     else:self.wfile.write(payload[start:])
   server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   try:
    s=Store(root/'data');s.add_source('https://youtu.be/BaW_jenozKc');w=Worker(s,reserve=0);j=s.claim(w.owner);output=root/'download.mp4'
    args=['yt-dlp','--ignore-config','--no-cache-dir','--retries','0','--socket-timeout','3','--continue','--output',str(output),'--',f'http://127.0.0.1:{server.server_port}/fixture.mp4']
    with self.assertRaises(Failure):w.run_command(args,j)
    partial=Path(str(output)+'.part');self.assertTrue(partial.exists());partial_size=partial.stat().st_size;self.assertGreater(partial_size,0);self.assertLess(partial_size,len(payload))
    state['drop']=False
    w.run_command(args,j);self.assertEqual(output.read_bytes(),payload);self.assertFalse(partial.exists());self.assertIn(partial_size,state['ranges']);w.validate(output,j)
   finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
