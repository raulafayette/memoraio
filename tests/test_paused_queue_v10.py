from pathlib import Path
import tempfile
import unittest
from memoria.core import Store
from memoria.exports import register_channel
from memoria.channels import start,control,status,refresh_catalog,advance
from memoria.worker import Worker

class PausedQueue(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.s=Store(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def add(self,name='fixture'):
        return register_channel(self.s,'https://youtube.com/@'+name,name)
    def channel(self,sid,store=None):return next(c for c in status(store or self.s)['channels'] if c['id']==sid)
    def test_registration_creates_a_paused_queue_entry_and_folder_without_jobs(self):
        sid=self.add();c=self.channel(sid);self.assertTrue(c['queue_paused']);self.assertIsNone(c['session']);self.assertTrue(Path(c['transcript_directory']).is_dir())
        self.assertEqual(self.s.tick(),[]);advance(self.s)
        self.assertFalse(Worker(self.s,reserve=0,lane='transcript').once())
        with self.s.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
    def test_queue_and_order_survive_restart(self):
        a=self.add('first');b=self.add('second');times=[self.channel(s)['queued_at'] for s in (a,b)]
        again=Store(self.tmp.name);self.assertTrue(self.channel(a,again)['queue_paused']);self.assertEqual(times,[self.channel(s,again)['queued_at'] for s in (a,b)]);self.assertLessEqual(times[0],times[1])
    def test_release_is_explicit_and_idempotent(self):
        sid=self.add();one=start(self.s,sid,scope='shorts');two=start(self.s,sid,scope='shorts');self.assertEqual(one,two);self.assertFalse(self.channel(sid)['queue_paused'])
        with self.s.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE kind='sync'").fetchone()[0],1)
    def test_refresh_counts_does_not_release_transcriptions(self):
        sid=self.add();refresh_catalog(self.s,sid);w=Worker(self.s,reserve=0,lane='acquire');self.assertTrue(w.once());advance(self.s)
        self.assertTrue(self.channel(sid)['queue_paused'])
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE kind IN ('transcribe','transcribe_asr','download','audio')").fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM channel_sessions').fetchone()[0],0)
    def test_duplicate_registration_preserves_existing_active_channel(self):
        sid=self.add();start(self.s,sid);before=self.channel(sid)['session']['id'];self.assertEqual(self.add(),sid)
        after=self.channel(sid);self.assertFalse(after['queue_paused']);self.assertEqual(after['session']['id'],before)
    def test_pause_moves_channel_back_and_resume_removes_only_its_queue_entry(self):
        one=self.add('one');two=self.add('two');start(self.s,one);control(self.s,one,'pause');again=Store(self.tmp.name)
        self.assertTrue(self.channel(one,again)['queue_paused']);control(again,one,'resume');self.assertFalse(self.channel(one,again)['queue_paused']);self.assertTrue(self.channel(two,again)['queue_paused'])
    def test_instagram_without_asr_stays_paused_after_failed_release(self):
        sid=register_channel(self.s,'https://instagram.com/example/','Example')
        with self.assertRaises(ValueError):start(self.s,sid,scope='public')
        self.assertTrue(self.channel(sid)['queue_paused'])
        with self.s.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
    def test_starting_a_media_download_does_not_release_transcript_queue(self):
        sid=self.add();start(self.s,sid,'video');self.assertTrue(self.channel(sid)['queue_paused']);self.assertIsNotNone(self.channel(sid)['media_session'])

if __name__=='__main__':unittest.main()
