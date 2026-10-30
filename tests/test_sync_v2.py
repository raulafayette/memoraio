from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from memoria.core import Store,SCHEMA,canonical,Failure,atomic_json,hash_file
from memoria.catalog import next_due
from memoria.sync import SyncEngine
from memoria.transcription import Transcriber,parse_json3,validate_transcript,export_transcript
from memoria.worker import Worker

class SyncTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.s=Store(self.root/'data')
  atomic_json(self.s.root/'bootstrap-sources.json',[(f'Fixture {i}',f'https://www.youtube.com/@fixture{i}') for i in range(7)]+[('Fixture Instagram','https://www.instagram.com/example/')])
 def tearDown(self):self.temp.cleanup()
 def seed(self):
  sid=self.s.register_source('https://youtube.com/@fixture',cadence='manual',auto_process=False)
  self.s.sync_now(sid);w=Worker(self.s,reserve=0);job=self.s.claim(w.owner);SyncEngine(w).start(job);self.s.finish(job,w.owner)
  with self.s.connect() as c:rid=c.execute('SELECT id FROM scan_runs').fetchone()[0]
  iid=self.s.observe(rid,{'id':'BaW_jenozKc','title':'Fonte de teste','duration':5,'channel':'Autor'})
  return sid,rid,iid
 def test_v1_migration_preserves_data(self):
  root=self.root/'old';root.mkdir();db=root/'catalog.sqlite3'
  with sqlite3.connect(db) as c:
   c.executescript(SCHEMA);c.execute('PRAGMA user_version=1');c.execute("INSERT INTO sources(id,url,scan_limit) VALUES('old','https://youtube.com/@old',50)")
  old=Store(root)
  with old.connect() as c:self.assertEqual(c.execute('SELECT id FROM sources').fetchone()[0],'old');self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],4)
  self.assertTrue(list((root/'backups').glob('*.sqlite3')))
 def test_official_eight_permanent_idempotent(self):
  a=self.s.bootstrap_official();b=self.s.bootstrap_official();self.assertEqual(a,b);self.assertEqual(len(a),8)
  with self.s.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM sources WHERE cadence='manual' AND auto_process=0").fetchone()[0],8)
  self.assertEqual(canonical('https://instagram.com/example/'),'https://www.instagram.com/example/')
 def test_calendar_month_and_intervals(self):
  stamp=datetime(2026,1,31,12,tzinfo=timezone.utc).timestamp();due=next_due(stamp,'monthly');self.assertEqual(datetime.fromtimestamp(due,timezone.utc).day,28)
  for cadence,days in [('daily',1),('weekly',7),('fortnightly',14)]:self.assertEqual(next_due(stamp,cadence)-stamp,86400*days)
  self.assertIsNone(next_due(stamp,'manual'))
 def test_due_catchup_once_and_manual_excluded(self):
  self.s.bootstrap_official();self.assertEqual(self.s.tick(),[])
  with self.s.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM jobs").fetchone()[0],0)
  restarted=Store(self.s.root);self.assertEqual(restarted.tick(),[])
 def test_rate_limit_cools_platform_not_other_sources_or_local_index(self):
  sid,rid,iid=self.seed();self.s.reprocess([iid])
  with self.s.connect() as c:c.execute("UPDATE jobs SET priority=200 WHERE kind='transcribe'")
  job=self.s.claim('w');self.s.finish(job,'w',Failure('429','rate_limited'))
  with self.s.connect() as c:
   self.assertEqual(c.execute('SELECT state FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],'retry')
   self.assertGreater(float(c.execute("SELECT value FROM service_state WHERE key='cooldown:youtube'").fetchone()[0]),time.time())
   embedding=self.s.enqueue(c,'embed','transcript-fixture')
  next_job=self.s.claim('other');self.assertEqual(next_job['id'],embedding)
 def test_pause_prevents_due_jobs(self):
  self.s.bootstrap_official()
  with self.s.connect() as c:c.execute("INSERT INTO service_state VALUES('paused','1')")
  self.assertEqual(self.s.tick(),[]);self.assertFalse(Worker(self.s,reserve=0).once())
 def test_observation_is_incremental_no_duplicate_and_no_false_removal(self):
  sid,rid,iid=self.seed();self.s.observe(rid,{'id':'BaW_jenozKc','title':'Alterado'});self.s.observe(rid,{'id':'BaW_jenozKc','title':'Alterado'});self.s.observe(rid,{'id':'00000000001','title':'Novo'})
  with self.s.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],2);self.assertEqual(c.execute('SELECT count(*) FROM run_items').fetchone()[0],2);self.assertEqual(c.execute('SELECT count(*) FROM versions').fetchone()[0],1)
  self.assertEqual(self.s.audit()[0]['inventory_state'],'partial')
 def test_method_failure_cannot_be_complete(self):
  sid,rid,iid=self.seed()
  with self.s.connect() as c:c.execute("UPDATE jobs SET state='failed' WHERE kind='enumerate'");c.execute("UPDATE scan_methods SET state='blocked',error='429' WHERE run_id=?",(rid,))
  SyncEngine(Worker(self.s,reserve=0)).reconcile();self.assertEqual(self.s.audit()[0]['inventory_state'],'partial')
 def test_methods_exhausted_still_unknown_platform_total(self):
  sid,rid,iid=self.seed()
  with self.s.connect() as c:c.execute("UPDATE jobs SET state='done' WHERE kind='enumerate'");c.execute("UPDATE scan_methods SET state='exhausted' WHERE run_id=?",(rid,))
  SyncEngine(Worker(self.s,reserve=0)).reconcile()
  with self.s.connect() as c:r=c.execute('SELECT * FROM scan_runs').fetchone();self.assertFalse(json.loads(r['summary'])['platform_total_known'])
  self.assertEqual(self.s.audit()[0]['inventory_state'],'enumerated_accessible')
 def test_offline_reprocess_uses_preserved_audio(self):
  sid,rid,iid=self.seed();audio=self.s.root/'originals'/'fixture.wav';audio.write_bytes(b'controlled-preserved-audio')
  with self.s.connect() as c:c.execute('INSERT INTO audio_assets VALUES(?,?,?,?,?)',(iid,str(audio.relative_to(self.s.root)),hash_file(audio),5,audio.stat().st_size))
  atomic_json(self.s.root/'asr-model.json',{'path':'controlled-model','revision':'fixture'})
  self.s.reprocess([iid],True)
  with self.s.connect() as c:c.execute("UPDATE jobs SET priority=200 WHERE kind='transcribe_asr'")
  w=Worker(self.s,reserve=0);job=self.s.claim(w.owner)
  def commands(args,job,cwd=None):
   if '--dump-single-json' in args:raise Failure('Fonte removida','failed')
   if 'memoria.asr' in args:
    target=Path(args[args.index('--output')+1]);target.mkdir(exist_ok=True)
    atomic_json(target/'result.json',{'segments':[{'start':0,'end':5,'text':'Texto da cópia local'}],'language':'pt','model':{'test_fixture':True}});return ''
   if 'memoria.speech_audit' in args:
    atomic_json(Path(args[args.index('--output')+1]),{'uncovered_speech_seconds':0,'uncovered_speech_ratio':0});return ''
   raise AssertionError(args)
  with patch.object(w,'run_command',side_effect=commands),patch('importlib.metadata.version',return_value='synthetic-test-engine'):Transcriber(w).run(job)
  self.s.finish(job,w.owner);self.assertEqual(len(self.s.search('cópia')),1)
 def test_worker_lanes_do_not_steal_other_stage(self):
  sid,rid,iid=self.seed()
  self.s.reprocess([iid])
  acquisition=self.s.claim('acq',kinds=('sync','enumerate','discover','download'));processing=self.s.claim('asr',kinds=('transcribe','transcribe_asr','embed'))
  self.assertEqual(acquisition['kind'],'enumerate');self.assertEqual(processing['kind'],'transcribe')
 def test_progress_chunks_do_not_exhaust_failure_budget(self):
  self.s.add_source('https://youtu.be/BaW_jenozKc')
  for _ in range(12):
   job=self.s.claim('worker');self.assertIsNotNone(job);self.s.finish(job,'worker',Failure('Cursor salvo','queued'))
   with self.s.connect() as c:c.execute('UPDATE jobs SET available=0');self.assertEqual(c.execute('SELECT attempts FROM jobs').fetchone()[0],0)
 def test_caption_publication_versioned_fts_palace_and_failure_preserves_previous(self):
  sid,rid,iid=self.seed();pid=self.s.palace('Audiovisual','Conhecimento',[sid]);w=Worker(self.s,reserve=0)
  def execute():
   self.s.reprocess([iid])
   with self.s.connect() as c:c.execute("UPDATE jobs SET priority=200 WHERE kind='transcribe'")
   job=self.s.claim(w.owner)
   segments=[{'start':0,'end':5,'text':'Montagem e silêncio narrativo'}];caption={'segments':segments,'language':'pt','origin':'manual_caption','model':None,'report':validate_transcript(segments,5)}
   with patch.object(w,'run_command',return_value=json.dumps({'id':'BaW_jenozKc','duration':5,'title':'Título real'})),patch.object(Transcriber,'captions',side_effect=[caption,None]):Transcriber(w).run(job)
   self.s.finish(job,w.owner)
  execute();execute()
  found=self.s.search('silêncio',pid);self.assertEqual(len(found),1);self.assertEqual(found[0]['item_id'],iid);self.assertEqual(found[0]['start'],0)
  self.assertEqual(self.s.search('silêncio','nonexistent'),[])
  with self.s.connect() as c:
   self.assertEqual(c.execute('SELECT count(*) FROM transcripts').fetchone()[0],2);self.assertEqual(c.execute('SELECT count(*) FROM transcripts WHERE current=1').fetchone()[0],1)
  self.assertEqual(self.s.audit()[0]['transcribed'],1)
  # A new failed attempt cannot erase a previous successful transcript.
  self.s.reprocess([iid]);
  with self.s.connect() as c:c.execute("UPDATE jobs SET priority=200 WHERE kind='transcribe'")
  job=self.s.claim(w.owner)
  with patch.object(w,'run_command',side_effect=Failure('offline')):
   with self.assertRaises(Failure):Transcriber(w).run(job)
  self.s.finish(job,w.owner,Failure('offline'));self.assertEqual(len(self.s.search('silêncio',pid)),1)
 def test_transcript_validation_and_exports(self):
  good=parse_json3({'events':[{'tStartMs':0,'dDurationMs':1000,'segs':[{'utf8':'Olá mundo'}]}]});self.assertEqual(validate_transcript(good,1)['quality'],'structural_pass')
  self.assertEqual(validate_transcript([],200)['quality'],'invalid')
  self.assertEqual(validate_transcript(good,200)['quality'],'needs_review')
  self.assertEqual(validate_transcript([{'start':float('nan'),'end':1,'text':'x'}],1)['quality'],'invalid')
  doc={'segments':good};export_transcript(self.root/'export',doc)
  self.assertEqual({x.suffix for x in (self.root/'export').iterdir()},{'.txt','.json','.srt','.vtt'})
 def test_instagram_carousel_identity_dedup(self):
  sid=self.s.register_source('https://instagram.com/example/',cadence='manual',auto_process=False)
  with self.s.connect() as c:c.execute("INSERT INTO scan_runs(id,source_id,started,state) VALUES('ig',?,?,'running')",(sid,time.time()))
  for child in [1,2,1]:self.s.observe('ig',{'id':'ABC_'+str(child),'webpage_url':'https://instagram.com/p/ABC/','title':'Carrossel'},'instagram')
  self.assertEqual(self.s.audit()[0]['identified'],2)
if __name__=='__main__':unittest.main()
