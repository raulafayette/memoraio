import concurrent.futures
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from memoria.core import Store,Failure,canonical,hash_file,atomic_json
from memoria.worker import Worker,classify
from memoria.server import Server
VIDEO='BaW_jenozKc'
URL='https://www.youtube.com/watch?v='+VIDEO
class Pipeline(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.s=Store(self.root/'archive')
 def tearDown(self):self.tmp.cleanup()
 def seed(self,n=1):
  self.s.add_source(URL)
  with self.s.connect() as c:sid=c.execute('SELECT id FROM sources').fetchone()[0]
  entries=[{'id':VIDEO if i==0 else f'{i:011d}','title':'Vídeo '+str(i),'duration':60} for i in range(n)]
  self.s.ingest(sid,entries);return sid,['youtube_'+x['id'] for x in entries]
 def finish_discovery(self):
  j=self.s.claim('seed');self.s.finish(j,'seed');return j
 def test_url_aliases_ssrf(self):
  for u in ['https://youtu.be/'+VIDEO+'?t=3','https://www.youtube.com/shorts/'+VIDEO,URL+'&t=4']:self.assertEqual(canonical(u),URL)
  for u in ['http://youtube.com/watch?v='+VIDEO,'https://localhost/test','https://youtube.com.evil.test/watch?v='+VIDEO,'https://user@youtube.com/watch?v='+VIDEO,'https://youtube.com:444/watch?v='+VIDEO,'https://instagram.com/a/b/c','file:///etc/passwd']:
   with self.assertRaises(ValueError):canonical(u)
 def test_duplicate_incremental_versions(self):
  sid,ids=self.seed();self.s.add_source('https://youtu.be/'+VIDEO);self.s.ingest(sid,[{'id':VIDEO,'title':'Alterado'}]);self.s.ingest(sid,[{'id':VIDEO,'title':'Alterado'},{'id':'00000000001','title':'Novo'}]);self.s.archive(ids);self.s.archive(ids)
  with self.s.connect() as c:
   for table,count in [('sources',1),('items',2),('versions',1)]:self.assertEqual(c.execute('SELECT count(*) FROM '+table).fetchone()[0],count)
   self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE kind='download'").fetchone()[0],1)
 def test_partial_scan_never_marks_removed(self):
  sid,ids=self.seed(3);self.s.ingest(sid,[{'id':VIDEO,'title':'Updated'}])
  with self.s.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM source_items').fetchone()[0],3)
 def test_concurrent_claim_unique(self):
  self.seed()
  with concurrent.futures.ThreadPoolExecutor(8) as pool:results=list(pool.map(lambda i:self.s.claim(str(i)),range(8)))
  self.assertEqual(sum(x is not None for x in results),1)
 def test_expired_lease_fencing(self):
  self.seed();old=self.s.claim('old',lease=-1);new=self.s.claim('new');self.s.finish(old,'old')
  with self.s.connect() as c:
   r=c.execute('SELECT * FROM jobs WHERE id=?',(old['id'],)).fetchone();self.assertEqual(r['owner'],'new');self.assertEqual(r['attempts'],2)
  self.s.finish(new,'new')
 def test_pause_cancel_resume(self):
  self.seed();j=self.s.claim('w');self.s.control(j['id'],'pause');self.s.finish(j,'w',Exception('pause'));self.assertEqual(self.s.snapshot()['jobs'][0]['state'],'paused');self.s.control(j['id'],'resume');self.s.control(j['id'],'cancel');self.assertEqual(self.s.snapshot()['jobs'][0]['state'],'cancelled');self.s.control(j['id'],'resume');self.assertEqual(self.s.claim('w')['id'],j['id'])
 def test_pending_control_survives_crash(self):
  self.seed();j=self.s.claim('w',lease=-1);self.s.control(j['id'],'pause');self.assertIsNone(self.s.claim('new'));self.assertEqual(self.s.snapshot()['jobs'][0]['state'],'paused')
 def test_retry_backoff_limit(self):
  self.seed()
  for attempt in range(4):
   j=self.s.claim('w');before=time.time();self.s.finish(j,'w',Failure('internet interrupted'))
   with self.s.connect() as c:
    r=c.execute('SELECT * FROM jobs WHERE id=?',(j['id'],)).fetchone();self.assertGreaterEqual(r['available']-before,5*2**(attempt+1));c.execute('UPDATE jobs SET available=0 WHERE id=?',(j['id'],))
  self.assertEqual(self.s.snapshot()['jobs'][0]['state'],'failed');self.assertIsNone(self.s.claim('w'))
 def test_error_isolation_classification(self):
  sid,ids=self.seed(2);self.finish_discovery();self.s.archive(ids);w=Worker(self.s,reserve=0)
  with patch.object(w,'download',side_effect=[Failure('gone','failed'),None]):self.assertTrue(w.once());self.assertTrue(w.once())
  states={j['state'] for j in self.s.snapshot()['jobs']};self.assertIn('done',states);self.assertIn('failed',states)
  for text,status in [('HTTP Error 429','rate_limited'),('Sign in to access','needs_auth'),('Video unavailable','failed')]:self.assertEqual(classify(text).state,status)
 def test_disk_reserve(self):
  self.seed();Worker(self.s,reserve=10**30).once();self.assertEqual(self.s.snapshot()['jobs'][0]['state'],'blocked')
 def test_database_lock(self):
  self.seed();c=self.s.connect();c.execute('BEGIN IMMEDIATE')
  with concurrent.futures.ThreadPoolExecutor(1) as pool:
   result=pool.submit(self.s.claim,'w');time.sleep(.1);self.assertFalse(result.done());c.rollback();self.assertIsNotNone(result.result(timeout=3))
  c.close()
 def test_thousand_items_idempotency(self):
  sid,ids=self.seed(1200);self.s.archive(ids);self.s.archive(ids)
  with self.s.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],1200);self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE kind='download'").fetchone()[0],1200)
 def test_backup_restore(self):
  self.seed();backup=self.s.backup();restored=Store(self.root/'restore');shutil.copy2(backup,restored.db);self.assertEqual(restored.snapshot()['stats']['items'],1)
  with restored.connect() as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
 def test_real_process_kill_recovery(self):
  self.seed();code='from memoria.core import Store; import sys,time; s=Store(sys.argv[1]); j=s.claim("child",lease=1); print(j["id"],flush=True); time.sleep(60)';p=subprocess.Popen([sys.executable,'-c',code,str(self.s.root)],stdout=subprocess.PIPE,text=True)
  try:
   jid=p.stdout.readline().strip();self.assertTrue(jid);p.kill();p.wait();time.sleep(1.1);recovered=self.s.claim('after_restart');self.assertEqual(recovered['id'],jid);self.assertEqual(recovered['attempts'],2)
  finally:
   if p.poll() is None:p.kill();p.wait()
   p.stdout.close()
 def test_atomic_json(self):
  path=self.root/'file.json';atomic_json(path,{'v':1});atomic_json(path,{'v':2});self.assertEqual(json.loads(path.read_text()),{'v':2});self.assertFalse(path.with_suffix('.tmp').exists())
 def test_real_media_checkpoint_partial(self):
  sid,ids=self.seed();self.finish_discovery();self.s.archive(ids);w=Worker(self.s,reserve=0);j=self.s.claim(w.owner);stage=self.s.root/'temporary'/ids[0];stage.mkdir();(stage/'media.mp4.part').write_bytes(b'incomplete');fixture=self.root/'fixture.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=64x64:d=0.2','-c:v','libx264','-y',str(fixture)],check=True);original=w.run_command
  def fake_extract(args,job,cwd=None):
   if args[0].endswith('yt-dlp') and '--version' in args:return 'fixture-extractor'
   if args[0].endswith('yt-dlp'):shutil.copyfile(fixture,stage/'media.mp4');return str(stage/'media.mp4')+'\n'
   return original(args,job,cwd)
  with patch.object(w,'run_command',side_effect=fake_extract):w.download(j)
  item=self.s.snapshot()['items'][0];self.assertEqual(item['status'],'archived');self.assertEqual(hash_file(self.s.root/item['path']),item['blob_hash'])
  with self.s.connect() as c:c.execute('UPDATE jobs SET lease_until=0 WHERE id=?',(j['id'],))
  j2=self.s.claim(w.owner)
  with patch.object(w,'run_command',side_effect=fake_extract):w.download(j2)
  self.s.finish(j2,w.owner);self.assertEqual(len(list((self.s.root/'originals').rglob('*.mp4'))),1)
  bad=self.root/'bad.mp4';bad.write_bytes(b'corrupt');self.s.add_source(URL);claimed=self.s.claim(w.owner)
  with self.assertRaises(Failure):w.validate(bad,claimed)
class HTTP(unittest.TestCase):
 def test_auth_origin_api(self):
  with tempfile.TemporaryDirectory() as d:
   server=Server(Store(d),0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();host=f'127.0.0.1:{server.server_port}';c=http.client.HTTPConnection(host)
   try:
    c.request('GET','/api/state');r=c.getresponse();self.assertEqual(r.status,403);r.read();c.request('GET','/?token='+server.token);r=c.getresponse();cookie=r.getheader('Set-Cookie').split(';')[0];self.assertEqual(r.status,303);r.read();c.request('GET','/',headers={'Cookie':cookie});r=c.getresponse();self.assertEqual(r.status,200);self.assertIn(b'Memoraio',r.read());data=json.dumps({'url':URL})
    c.request('POST','/api/sources',data,{'Cookie':cookie,'Content-Type':'application/json','Origin':'https://evil.test'});r=c.getresponse();self.assertEqual(r.status,403);r.read();c.request('POST','/api/sources',data,{'Cookie':cookie,'Content-Type':'application/json','Origin':'http://'+host});r=c.getresponse();self.assertEqual(r.status,200);r.read();c.request('GET','/api/state',headers={'Cookie':cookie});r=c.getresponse();s=json.loads(r.read());self.assertEqual(len(s['sources']),1);c.request('GET','/api/state',headers={'Cookie':cookie,'Host':'evil.test'});r=c.getresponse();self.assertEqual(r.status,403);r.read()
   finally:c.close();server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
