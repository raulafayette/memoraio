from datetime import datetime,timezone
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from memoria.core import Store,Interrupted
from memoria.channels import start,control,advance,refresh_catalog,status
from memoria.channel_ui import begin_review,review,news,control_state,batch_start
from memoria.exports import register_channel,locations,publish as export
from memoria.preferences import save
from memoria.sync import SyncEngine
from memoria.worker import Worker
from tests.test_channels_v5 import publish,A,B

class Workspace(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def source(self,name='one'):
        sid=register_channel(self.s,'https://youtube.com/@'+name,name);return sid
    def scan(self,sid,rid,entries,finished=True):
        with self.s.connect() as c:
            c.execute('INSERT INTO scan_runs(id,source_id,started,finished,state) VALUES(?,?,?,?,?)',(rid,sid,time.time(),time.time() if finished else None,'enumerated_accessible' if finished else 'running'));begin_review(c,rid,sid)
        for iid in entries:self.s.observe(rid,{'id':iid,'title':'Conteúdo '+iid})
    def test_first_inventory_is_not_misrepresented_as_new_publications(self):
        sid=self.source();self.scan(sid,'first',[A])
        with self.s.connect() as c:r=review(c,sid)
        self.assertTrue(r['initial']);self.assertEqual(r['new_count'],1)
    def test_repeat_check_reports_only_distinct_new_items_and_persists(self):
        sid=self.source();self.scan(sid,'first',[A]);self.scan(sid,'second',[A,B,B]);again=Store(self.tmp.name)
        with again.connect() as c:r=review(c,sid)
        self.assertFalse(r['initial']);self.assertEqual(r['new_count'],1);self.assertEqual(news(again,sid)['items'][0]['id'],'youtube_'+B)
        self.scan(sid,'third',[A,B])
        with self.s.connect() as c:self.assertEqual(review(c,sid)['new_count'],0)
    def test_partial_review_keeps_partial_status(self):
        sid=self.source();self.scan(sid,'first',[A]);self.scan(sid,'partial',[B],False)
        with self.s.connect() as c:self.assertTrue(review(c,sid)['partial'])
    def test_pause_then_immediate_play_does_not_leave_a_stranded_job(self):
        sid=self.source();self.s.ingest(sid,[{'id':A}]);start(self.s,sid);advance(self.s);job=self.s.claim('worker',kinds=('transcribe',))
        control(self.s,sid,'pause');self.assertEqual(control_state(self.s,sid)['stopping'],1)
        control(self.s,sid,'resume');self.s.finish(job,'worker',Interrupted('pause'))
        with self.s.connect() as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(job['id'],)).fetchone()
        self.assertEqual(r['state'],'queued');self.assertLessEqual(r['available'],time.time());self.assertFalse(control_state(self.s,sid)['queue_paused'])
    def test_pause_is_atomic_and_keeps_other_channel_running(self):
        one=self.source('one');two=self.source('two')
        for sid in (one,two):self.s.ingest(sid,[{'id':A if sid==one else B}]);start(self.s,sid)
        advance(self.s);entered=threading.Event();release=threading.Event();original=self.s.event
        def event(c,jid,kind,detail):
            original(c,jid,kind,detail)
            if kind=='control' and not entered.is_set():entered.set();release.wait(5)
        with patch.object(self.s,'event',event):
            t=threading.Thread(target=control,args=(self.s,one,'pause'));t.start();self.assertTrue(entered.wait(3))
            with self.s.connect() as c:self.assertEqual(c.execute('SELECT state FROM channel_sessions WHERE source_id=?',(one,)).fetchone()[0],'discovering')
            release.set();t.join(5);self.assertFalse(t.is_alive())
        self.assertTrue(control_state(self.s,one)['queue_paused']);self.assertFalse(control_state(self.s,two)['queue_paused'])
    def test_metadata_check_while_paused_never_resumes_transcriptions(self):
        sid=self.source();start(self.s,sid);w=Worker(self.s,reserve=0,lane='acquire');job=self.s.claim(w.owner,kinds=('sync',));SyncEngine(w).start(job);self.s.finish(job,w.owner);control(self.s,sid,'pause')
        old=control_state(self.s,sid)['session_id'];jid=refresh_catalog(self.s,sid)
        with self.s.connect() as c:self.assertEqual(c.execute('SELECT kind FROM jobs WHERE id=?',(jid,)).fetchone()[0],'catalog_sync')
        job=self.s.claim(w.owner,kinds=('catalog_sync',));SyncEngine(w).start(job);self.s.finish(job,w.owner);advance(self.s)
        self.assertEqual(control_state(self.s,sid)['session_id'],old);self.assertTrue(control_state(self.s,sid)['queue_paused'])
        with self.s.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE kind='transcribe'").fetchone()[0],0)
    def test_collective_play_does_not_start_unselected_channels_or_pause_active_ones(self):
        ids=[self.source('s'+str(i)) for i in range(4)];result=batch_start(self.s,ids[:2]);self.assertTrue(all(r['ok'] for r in result));old=control_state(self.s,ids[0])['session_id'];batch_start(self.s,ids[:2]);self.assertEqual(control_state(self.s,ids[0])['session_id'],old)
        self.assertTrue(control_state(self.s,ids[2])['queue_paused']);control(self.s,ids[1],'pause');batch_start(self.s);self.assertTrue(all(not control_state(self.s,i)['queue_paused'] for i in ids))
    def test_bulk_reports_a_bad_channel_without_losing_good_requests(self):
        one=self.source();result=batch_start(self.s,['unknown',one]);self.assertFalse(result[0]['ok']);self.assertTrue(result[1]['ok'])
    def test_month_uses_completion_time_and_timezone_even_when_copied_later(self):
        sid=self.source();self.s.ingest(sid,[{'id':A,'title':'Mensal'}]);publish(self.s,'youtube_'+A)
        completed=datetime(2026,11,1,1,tzinfo=timezone.utc).timestamp();save(self.s,{'archive_timezone':'America/Fortaleza'})
        with self.s.connect() as c:c.execute('UPDATE transcripts SET created=?',(completed,))
        result=export(self.s,sid,'youtube_'+A);self.assertEqual(Path(result['path']).parent.name,'2026-10');self.assertTrue(Path(result['path']).is_file());self.assertEqual(locations(self.s,sid)['youtube_'+A]['path'],result['path'])
    def test_reorganization_removes_only_identical_owned_flat_copies(self):
        sid=self.source();self.s.ingest(sid,[{'id':A,'title':'Mensal'}]);publish(self.s,'youtube_'+A);iid='youtube_'+A;current=Path(locations(self.s,sid)[iid]['path']);flat=current.parent.parent/current.name;flat.write_bytes(current.read_bytes())
        from memoria.core import hash_file
        with self.s.connect() as c:c.execute('INSERT INTO text_exports SELECT source_id,item_id,transcript_id,?,sha256,created,0 FROM text_exports WHERE path=?',(str(flat),str(current)))
        export(self.s,sid,iid);self.assertFalse(flat.exists());flat.write_text('Minha anotação');export(self.s,sid,iid);self.assertEqual(flat.read_text(),'Minha anotação');self.assertTrue(hash_file(current))
    def test_repeated_export_does_not_rewrite_or_redownload_a_valid_txt(self):
        sid=self.source();self.s.ingest(sid,[{'id':A}]);publish(self.s,'youtube_'+A);p=Path(locations(self.s,sid)['youtube_'+A]['path']);stamp=p.stat().st_mtime_ns;export(self.s,sid,'youtube_'+A);self.assertEqual(p.stat().st_mtime_ns,stamp)
    def test_mp3_mp4_shortcuts_use_completion_month_and_preserve_media_objects(self):
        import json
        from memoria.core import atomic_json,hash_file
        from memoria.channels import folder
        sid=self.source();iid='youtube_'+A;self.s.ingest(sid,[{'id':A,'title':'Mídia mensal'}]);file=self.s.root/'originals'/'fixture.mp4';file.write_bytes(b'controlled media');digest=hash_file(file);date=datetime(2026,10,12,tzinfo=timezone.utc).timestamp()
        with self.s.connect() as c:
            c.execute('UPDATE items SET path=?,blob_hash=? WHERE id=?',(str(file.relative_to(self.s.root)),digest,iid))
            c.execute('INSERT INTO service_state VALUES(?,?)',('mp3:'+iid,json.dumps({'path':str(file.relative_to(self.s.root)),'sha256':digest})))
            source=dict(c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone())
        directory=self.s.root/'metadata'/'assets'/iid;directory.mkdir(parents=True)
        for kind in ('video','mp3'):atomic_json(directory/(kind+'-fixture.json'),{'collected_at':date})
        from memoria.monthly import queue_organization
        self.assertEqual(queue_organization(self.s)['media_items'],1)
        self.assertTrue(Worker(self.s,reserve=0,lane='organizer').once())
        for kind in ('videos','musicas'):
            paths=list((folder(self.s,source)/kind/'2026-10').iterdir());self.assertEqual(len(paths),1);self.assertTrue(paths[0].is_symlink());self.assertEqual(paths[0].resolve(),file.resolve())
        self.assertTrue(file.is_file())
    def test_media_manager_does_not_probe_the_transcription_only_catalog(self):
        from memoria.inventory import inventory,assets
        from memoria.core import hash_file
        sid=self.source();self.s.ingest(sid,[{'id':A},{'id':B}]);file=self.s.root/'originals'/'movie.mp4';file.write_bytes(b'verified fixture media')
        with self.s.connect() as c:c.execute('UPDATE items SET path=?,blob_hash=? WHERE id=?',(str(file.relative_to(self.s.root)),hash_file(file),'youtube_'+B))
        with patch('memoria.inventory.assets',wraps=assets) as probe:r=inventory(self.s,{'group':['saved'],'media_only':['1']})
        self.assertEqual(probe.call_count,1);self.assertEqual(r['counts']['video'],1);self.assertEqual(r['items'][0]['id'],'youtube_'+B)
    def test_unique_overview_deduplicates_shared_items(self):
        one=self.source('one');two=self.source('two')
        for sid in (one,two):self.s.ingest(sid,[{'id':A}])
        publish(self.s,'youtube_'+A);s=status(self.s);self.assertEqual(s['overview']['identified'],1);self.assertEqual(s['overview']['ready'],1)

if __name__=='__main__':unittest.main()
