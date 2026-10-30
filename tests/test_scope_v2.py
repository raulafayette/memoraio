import tempfile
import unittest
from unittest.mock import patch
from memoria.core import Store
from memoria.worker import Worker
from memoria.sync import SyncEngine

class Scope(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name)
  self.sid=self.s.register_source('https://youtube.com/@fixture',cadence='manual',auto_process=False)
  self.s.sync_now(self.sid);self.w=Worker(self.s,reserve=0);j=self.s.claim(self.w.owner);SyncEngine(self.w).start(j);self.s.finish(j,self.w.owner)
  with self.s.connect() as c:
   self.rid=c.execute('SELECT id FROM scan_runs').fetchone()[0]
   c.execute('INSERT INTO service_state VALUES(?,?)',('channel:'+self.sid,'UC'+'a'*22))
 def tearDown(self):self.tmp.cleanup()
 def test_sync_uses_pinned_channel_not_reassignable_handle(self):
  with self.s.connect() as c:c.execute("UPDATE scan_runs SET state='partial'")
  self.s.sync_now(self.sid);job=self.s.claim(self.w.owner);SyncEngine(self.w).start(job)
  with self.s.connect() as c:
   rid=c.execute('SELECT id FROM scan_runs ORDER BY started DESC LIMIT 1').fetchone()[0]
   urls=[r[0] for r in c.execute('SELECT url FROM scan_methods WHERE run_id=?',(rid,))]
  self.assertEqual(len(urls),5);self.assertTrue(all('/channel/UC'+'a'*22 in u for u in urls))
 def test_snapshot_coverage_is_transactionally_consistent(self):
  import threading
  errors=[]
  def write():
   try:
    for i in range(100):self.s.observe(self.rid,{'id':f'{i:011d}','title':'Item'})
   except Exception as e:errors.append(e)
  thread=threading.Thread(target=write);thread.start()
  for _ in range(20):
   snapshot=self.s.snapshot();self.assertEqual(snapshot['stats']['items'],snapshot['audit'][0]['identified'])
  thread.join();self.assertEqual(errors,[])
 def test_playlist_video_author_does_not_expand_other_uploads(self):
  with self.s.connect() as c:mid=self.s.add_method(c,self.rid,'youtube_playlist','https://www.youtube.com/playlist?list=PLfixture12345')
  def stream(args,job,consume,timeout=7200):
   consume({'id':'BaW_jenozKc','title':'Vídeo listado','channel_id':'UC'+'b'*22});return ''
  with patch.object(SyncEngine,'stream',side_effect=stream):SyncEngine(self.w).enumerate({'id':'test','target':mid})
  with self.s.connect() as c:
   self.assertEqual(c.execute("SELECT count(*) FROM scan_methods WHERE method='youtube_uploads'").fetchone()[0],0)
   self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],1)
 def test_uploads_require_verified_original_channel(self):
  with self.s.connect() as c:
   with self.assertRaises(ValueError):self.s.add_method(c,self.rid,'youtube_uploads','https://www.youtube.com/playlist?list=UU'+'b'*22)
   mid=self.s.add_method(c,self.rid,'youtube_uploads','https://www.youtube.com/playlist?list=UU'+'a'*22)
   self.assertTrue(mid)
 def test_scope_repair_keeps_records_and_excludes_processing(self):
  good=self.s.observe(self.rid,{'id':'BaW_jenozKc','title':'Correto'})
  bad=self.s.observe(self.rid,{'id':'00000000001','title':'Expansão indevida'})
  with self.s.connect() as c:
   original=c.execute("SELECT id FROM scan_methods WHERE method='youtube_videos'").fetchone()[0]
   c.execute('INSERT INTO method_items VALUES(?,?)',(original,good))
   c.execute("INSERT INTO scan_methods(id,run_id,method,url,state) VALUES('bad',?,'youtube_uploads',?,'exhausted')",(self.rid,'https://www.youtube.com/playlist?list=UU'+'b'*22))
   for iid in (good,bad):c.execute('INSERT INTO method_items VALUES(?,?)',('bad',iid))
  self.s.reprocess([bad]);result=self.s.repair_scope()
  self.assertFalse(result['data_deleted']);self.assertEqual(result['quarantined_associations'],1);self.assertEqual(result['cancelled_processing_jobs'],1)
  with self.assertRaises(ValueError):self.s.reprocess([bad])
  self.assertEqual(self.s.audit()[0]['identified'],1);self.assertEqual(self.s.snapshot()['stats']['items'],1)
  with self.s.connect() as c:
   self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],2)
   self.assertEqual(c.execute('SELECT count(*) FROM source_items').fetchone()[0],2)
   self.assertEqual(c.execute("SELECT state FROM jobs WHERE kind='transcribe'").fetchone()[0],'cancelled')
   jid=self.s.enqueue(c,'enumerate','bad')
  with self.assertRaises(ValueError):
   # A cancelled out-of-scope enumeration cannot be revived by the normal UI.
   with self.s.connect() as c:c.execute("UPDATE jobs SET state='cancelled' WHERE id=?",(jid,))
   self.s.control(jid,'resume')
if __name__=='__main__':unittest.main()
