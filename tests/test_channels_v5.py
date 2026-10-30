import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from memoria.core import Store,atomic_json,hash_file
from memoria.channels import start,advance,status,control,link_files
from memoria.sync import SyncEngine
from memoria.worker import Worker
from memoria.transcription import Transcriber,validate_transcript
from memoria.library import publish_library

A='BaW_jenozKc';B='abcdefghijk';C='12345678901'

def fixture(store):
    one=store.register_source('https://youtube.com/@canalteste','Canal Um')
    two=store.register_source('https://youtube.com/@outroteste','Canal Dois')
    return one,two

def publish(store,iid):
    tid=__import__('uuid').uuid4().hex;p=store.root/'transcripts'/iid/tid/'transcript.json';p.parent.mkdir(parents=True)
    atomic_json(p,{'id':tid,'segments':[{'start':0,'end':2,'text':'Texto integral controlado do canal.'}],'origin':'manual_caption','duration':2})
    with store.connect() as c:
        c.execute('UPDATE transcripts SET current=0 WHERE item_id=?',(iid,))
        c.execute('INSERT INTO transcripts VALUES(?,?,?,?,?,?,?,?,?,?,1)',(tid,iid,time.time(),'manual_caption','pt','null',str(p.relative_to(store.root)),hash_file(p),'structural_pass','{}'))
    publish_library(store,iid);link_files(store,iid)

def mock_stream(args,job,consume,timeout=7200):
    url=args[-1]
    for oid in ([A,B,C] if '/playlist?' in url else [B] if url.endswith('/shorts') else [C] if url.endswith('/streams') else [A]):
        consume({'id':oid,'title':('Short controlado' if oid==B else 'Live controlada' if oid==C else 'Vídeo controlado'),'duration':2})
    return ''

def scan(store,sid,scope='all',mode='transcript'):
    session=start(store,sid,mode,scope);w=Worker(store,reserve=0,lane='acquire')
    with patch.object(SyncEngine,'stream',side_effect=mock_stream),patch.object(w,'run_command',return_value=json.dumps({'channel_id':'UC'+'x'*22})):
        for _ in range(12):
            with store.connect() as c:pending=c.execute("SELECT 1 FROM jobs WHERE kind IN ('sync','enumerate') AND state IN ('queued','retry') AND available<=?",(time.time(),)).fetchone()
            if not pending:break
            w.once()
    advance(store)
    return session

class ChannelRuns(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name);self.one,self.two=fixture(self.s)
    def tearDown(self):self.tmp.cleanup()
    def test_nothing_starts_until_play_and_double_click_is_idempotent(self):
        self.assertEqual(self.s.tick(),[])
        with self.s.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(lambda _:start(self.s,self.one,scope='shorts'),range(2)))
        self.assertEqual(ids[0],ids[1])
        with self.s.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
        self.assertIsNone(status(self.s)['channels'][1]['session'])
    def test_selected_shorts_are_the_only_items_queued(self):
        scan(self.s,self.one,'shorts')
        with self.s.connect() as c:
            methods={r[0] for r in c.execute('SELECT method FROM scan_methods')}
            self.assertEqual(methods,{'youtube_identity','youtube_shorts'})
            queued=[r[0] for r in c.execute("SELECT target FROM jobs WHERE kind='transcribe'")]
            self.assertEqual(queued,['youtube_'+B])
        ch=status(self.s)['channels'];self.assertEqual(ch[0]['session']['total'],1);self.assertEqual(ch[0]['session']['counts']['queued'],1);self.assertEqual(ch[1]['identified'],0)
    def test_all_scopes_and_real_caption_publication_then_incremental_skip(self):
        first=scan(self.s,self.one)
        w=Worker(self.s,reserve=0,lane='process');segments=[{'start':0,'end':2,'text':'Texto completo controlado.'}]
        caption={'segments':segments,'language':'pt','origin':'manual_caption','model':None,'report':validate_transcript(segments,2)}
        with patch.object(w,'run_command',return_value=json.dumps({'duration':2})),patch.object(Transcriber,'captions',return_value=caption):
            for _ in range(15):
                if not w.once():break
        advance(self.s);ch=status(self.s)['channels'][0]
        self.assertEqual(ch['session']['state'],'finished');self.assertEqual(ch['ready'],3)
        files=list(Path(ch['folder']).glob('transcricoes/*/*.txt'));self.assertEqual(len(files),3);self.assertTrue(all(p.is_file() for p in files))
        second=scan(self.s,self.one,'videos');self.assertNotEqual(first,second);advance(self.s)
        ch=status(self.s)['channels'][0];self.assertEqual(ch['session']['total'],1);self.assertEqual(ch['session']['counts']['ready'],1)
        with self.s.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE kind='transcribe'").fetchone()[0],3)
    def test_pause_resume_and_cancel_are_channel_scoped(self):
        start(self.s,self.one,scope='videos');other=start(self.s,self.two,scope='shorts')
        control(self.s,self.one,'pause');job=self.s.claim('other',kinds=('sync',));self.assertEqual(job['target'],self.two)
        control(self.s,self.one,'resume');job=self.s.claim('one',kinds=('sync',));self.assertEqual(job['target'],self.one)
        control(self.s,self.one,'cancel')
        with self.s.connect() as c:self.assertEqual(c.execute('SELECT state FROM channel_sessions WHERE id=?',(other,)).fetchone()[0],'discovering')
    def test_restart_after_discovery_recovers_planning_without_duplicate_jobs(self):
        session=start(self.s,self.one,'transcript','videos');w=Worker(self.s,reserve=0,lane='acquire');j=self.s.claim(w.owner,kinds=('sync',));SyncEngine(w).start(j);self.s.finish(j,w.owner)
        with self.s.connect() as c:rid=c.execute('SELECT scan_id FROM channel_sessions WHERE id=?',(session,)).fetchone()[0];mid=c.execute("SELECT id FROM scan_methods WHERE run_id=? AND method='youtube_videos'",(rid,)).fetchone()[0]
        iid=self.s.observe(rid,{'id':A,'title':'Vídeo integral'})
        with self.s.connect() as c:
            c.execute('INSERT INTO method_items VALUES(?,?)',(mid,iid));c.execute("UPDATE scan_runs SET state='enumerated_accessible' WHERE id=?",(rid,));c.execute("UPDATE jobs SET state='done' WHERE kind='enumerate'")
        restarted=Store(self.tmp.name);advance(restarted);advance(Store(self.tmp.name))
        with restarted.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE kind='transcribe'").fetchone()[0],1);self.assertEqual(c.execute('SELECT count(*) FROM session_items').fetchone()[0],1)
    def test_expired_lease_and_partial_file_do_not_count_as_completed(self):
        scan(self.s,self.one,'videos');job=self.s.claim('lost-worker',kinds=('transcribe',));stage=self.s.root/'temporary'/'partial.txt.part';stage.write_text('incompleto')
        with self.s.connect() as c:c.execute('UPDATE jobs SET lease_until=1 WHERE id=?',(job['id'],))
        restarted=Store(self.tmp.name);recovered=restarted.claim('replacement',kinds=('transcribe',));self.assertEqual(recovered['id'],job['id'])
        self.assertEqual(status(restarted)['channels'][0]['ready'],0);self.assertEqual(status(restarted)['channels'][0]['session']['counts']['running'],1)
    def test_file_altered_on_disk_is_redownloaded_on_next_play(self):
        scan(self.s,self.one,'videos');publish(self.s,'youtube_'+A)
        with self.s.connect() as c:c.execute("UPDATE jobs SET state='done' WHERE kind='transcribe'")
        advance(self.s)
        from memoria.inventory import inventory
        canonical=inventory(self.s,{'group':['ready']})['items'][0]['assets']['txt']['path']
        Path(canonical).write_text('alterado')
        self.assertEqual(status(self.s)['channels'][0]['ready'],0)
        scan(self.s,self.one,'videos')
        with self.s.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE kind='transcribe' AND state='queued'").fetchone()[0],1)
    def test_sqlite_recovers_an_uncommitted_process_exit(self):
        self.s.ingest(self.one,[{'id':A,'title':'Registro íntegro'}])
        script="import sqlite3,os,sys;c=sqlite3.connect(sys.argv[1]);c.execute('BEGIN IMMEDIATE');c.execute(\"UPDATE items SET path='incompleto.mp4',status='archived'\");os._exit(97)"
        r=subprocess.run([sys.executable,'-c',script,str(self.s.db)]);self.assertEqual(r.returncode,97)
        restored=Store(self.tmp.name)
        with restored.connect() as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertIsNone(c.execute('SELECT path FROM items').fetchone()[0])

    def test_playlist_url_expands_automatically_into_three_mp3_jobs(self):
        sid=self.s.register_source('https://www.youtube.com/playlist?list=PLfixture123456')
        scan(self.s,sid,mode='mp3')
        with self.s.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM session_items').fetchone()[0],3)
            self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE kind='audio'").fetchone()[0],3)
            opts=[json.loads(r[0]) for r in c.execute("SELECT value FROM service_state WHERE key LIKE 'job_options:%'")]
            self.assertTrue(all(o['audio_format']=='mp3' for o in opts))
    def test_single_video_stays_single_and_active_format_change_is_explicit(self):
        sid=self.s.register_source('https://youtu.be/'+A);scan(self.s,sid,mode='video')
        with self.s.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM session_items').fetchone()[0],1)
        self.assertRaises(ValueError,start,self.s,sid,'mp3','all')

    def test_failed_caption_is_not_a_completed_download(self):
        scan(self.s,self.one,'shorts')
        with self.s.connect() as c:c.execute("UPDATE jobs SET state='blocked' WHERE kind='transcribe'")
        advance(self.s);session=status(self.s)['channels'][0]['session']
        self.assertEqual(session['state'],'finished');self.assertEqual(session['counts']['ready'],0);self.assertEqual(session['counts']['unavailable'],1)
    def test_media_batch_never_appears_as_transcript_progress(self):
        scan(self.s,self.one,'videos',mode='video');ch=status(self.s)['channels'][0]
        self.assertIsNone(ch['session']);self.assertEqual(ch['media_session']['mode'],'video');self.assertEqual(ch['ready'],0)
