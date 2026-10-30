import concurrent.futures
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from memoria.core import Store
from memoria.channels import start,advance,status
from memoria.service import service_commands,check_worker_health,set_paused
from memoria.transcription import Transcriber,validate_transcript
from memoria.worker import Worker

KINDS=('transcribe','transcribe_asr')

class ParallelChannels(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def seed(self,count=4,per_source=2):
        sources=[]
        for n in range(count):
            sid=self.store.register_source('https://youtube.com/@fixture'+str(n),'Canal '+str(n));sources.append(sid)
            self.store.ingest(sid,[{'id':f'{n:02}{i:09}','title':f'Vídeo {n} / {i}'} for i in range(per_source)])
            start(self.store,sid)
        advance(self.store)
        return sources
    def claim(self,owner):return self.store.claim(owner,kinds=KINDS,channel_lane='transcript')
    def source_of(self,job):
        with self.store.connect() as c:return c.execute('SELECT source_id FROM job_sources WHERE id=?',(job['id'],)).fetchone()[0]
    def test_service_has_three_independent_channels_and_separate_local_publication(self):
        commands=dict(service_commands(8765))
        self.assertEqual(sum(v==['worker','--lane','transcript'] for v in commands.values()),3)
        self.assertEqual(sum(v==['worker','--lane','acquire'] for v in commands.values()),3)
        self.assertEqual(commands['maintenance'],['worker','--lane','maintenance'])
    def test_three_simultaneous_claims_choose_different_channels_and_never_duplicate(self):
        self.seed()
        with concurrent.futures.ThreadPoolExecutor(3) as pool:jobs=list(pool.map(self.claim,['one','two','three']))
        self.assertEqual(len({j['id'] for j in jobs}),3)
        self.assertEqual(len({self.source_of(j) for j in jobs}),3)
        for j in jobs:self.assertEqual(j['state'],'running')
    def test_one_channel_cannot_occupy_all_slots(self):
        self.seed(count=1);first=self.claim('one');self.assertIsNotNone(first);self.assertIsNone(self.claim('two'))
        self.store.finish(first,'one');self.assertIsNotNone(self.claim('two'))
    def test_fourth_channel_gets_next_free_slot_before_large_channel_repeats(self):
        sources=self.seed();jobs=[self.claim(x) for x in ['one','two','three']];busy={self.source_of(j) for j in jobs}
        self.store.finish(jobs[0],'one');next_job=self.claim('next')
        self.assertEqual(self.source_of(next_job),next(s for s in sources if s not in busy))
    def test_paused_channel_is_not_started_and_global_pause_closes_claim_race(self):
        sources=self.seed(count=3)
        from memoria.channels import control
        control(self.store,sources[0],'pause');jobs=[self.claim(x) for x in ['one','two']]
        self.assertNotIn(sources[0],{self.source_of(j) for j in jobs})
        set_paused(self.store,True);self.assertIsNone(self.claim('three'));set_paused(self.store,False)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT state FROM channel_sessions WHERE source_id=?',(sources[0],)).fetchone()[0],'paused')
    def test_expired_lease_releases_channel_and_same_job_is_recoverable(self):
        self.seed(count=1,per_source=1);old=self.claim('lost')
        with self.store.connect() as c:c.execute('UPDATE jobs SET lease_until=1 WHERE id=?',(old['id'],))
        recovered=self.claim('replacement');self.assertEqual(recovered['id'],old['id'])
    def test_watchdog_covers_all_parallel_slots(self):
        calls=[];now=time.time();children={k:SimpleNamespace(pid=100+i,poll=lambda:None,terminate=lambda key=k:calls.append(key)) for i,k in enumerate(['acquisition-3','processing-2','processing-3','maintenance'])}
        check_worker_health(self.store,children,{k:now-200 for k in children},now)
        self.assertEqual(set(calls),set(children))
    def test_three_actual_pipelines_overlap_and_publish_separate_verified_txt(self):
        self.seed(count=3,per_source=1);barrier=threading.Barrier(3);overlapped=[]
        segments=[{'start':0,'end':2,'text':'Fala completa de um vídeo de teste.'}]
        def captions(engine,item,info,job,directory,automatic):
            overlapped.append(item['id']);barrier.wait(timeout=15)
            return {'segments':segments,'language':'pt','origin':'manual_caption','model':None,'report':validate_transcript(segments,2)}
        workers=[Worker(self.store,reserve=0,lane='transcript') for _ in range(3)]
        with patch.object(Worker,'run_command',return_value=json.dumps({'duration':2,'language':'pt'})),patch.object(Transcriber,'captions',captions):
            with concurrent.futures.ThreadPoolExecutor(3) as pool:results=list(pool.map(lambda w:w.once(),workers))
        self.assertEqual(results,[True,True,True]);self.assertEqual(len(set(overlapped)),3)
        local=Worker(self.store,reserve=0,lane='maintenance')
        for _ in range(5):
            if not local.once():break
        channels=status(self.store)['channels'];self.assertEqual([c['ready'] for c in channels],[1,1,1])
        for c in channels:self.assertEqual(len(list(Path(c['transcript_directory']).rglob('*.txt'))),1)
        with self.store.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE kind='transcribe' AND state='done'").fetchone()[0],3)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')

if __name__=='__main__':unittest.main()
