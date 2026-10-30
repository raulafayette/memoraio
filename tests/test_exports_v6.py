from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from memoria.core import Store
from memoria.exports import register_channel,set_source_directory,source_directory,locations,publish as export
from memoria.preferences import save
from memoria.statistics import summary
from memoria.channels import start,advance
from tests.test_channels_v5 import publish,A

class ExportsAndCounts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name).resolve();self.store=Store(self.home/'data');self.destination=self.home/'chosen';self.destination.mkdir();self.home_patch=patch('pathlib.Path.home',return_value=self.home);self.home_patch.start()
    def tearDown(self):self.home_patch.stop();self.tmp.cleanup()
    def source(self):
        sid=register_channel(self.store,'https://youtube.com/@fixture','Canal seguro')
        with self.store.connect() as c:return dict(c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone())
    def test_new_source_folder_and_overrides_preserve_old_text_and_user_edit(self):
        save(self.store,{'transcript_directory':str(self.destination)})
        s=self.source();directory=source_directory(self.store,s);self.assertTrue(directory.is_dir());self.assertTrue(directory.is_relative_to(self.destination))
        self.store.ingest(s['id'],[{'id':A,'title':'Título'}]);iid='youtube_'+A;publish(self.store,iid)
        original=Path(locations(self.store,s['id'])[iid]['path']);self.assertTrue(original.is_file());self.assertFalse(original.is_symlink())
        another=self.home/'another';another.mkdir();set_source_directory(self.store,s['id'],str(another));export(self.store,s['id'],iid)
        current=Path(locations(self.store,s['id'])[iid]['path']);self.assertEqual(current.parent.parent,another);self.assertTrue(original.is_file())
        current.write_text('Minha anotação pessoal');export(self.store,s['id'],iid)
        self.assertEqual(current.read_text(),'Minha anotação pessoal');self.assertNotEqual(locations(self.store,s['id'])[iid]['path'],str(current))
    def test_bad_directory_types_and_internal_destinations_rejected(self):
        s=self.source()
        for value in (None,False,42):
            with self.assertRaises(ValueError):save(self.store,{'transcript_directory':value})
            with self.assertRaises(ValueError):set_source_directory(self.store,s['id'],value)
        with self.assertRaises(ValueError):save(self.store,{'transcript_directory':str(self.store.root/'originals')})
    def test_statistics_dedup_and_first_publication_in_local_timezone(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        s=self.source();self.store.ingest(s['id'],[{'id':A,'title':'Título'}]);iid='youtube_'+A
        publish(self.store,iid)
        now=datetime(2026,10,29,12,tzinfo=ZoneInfo('America/Fortaleza')).timestamp()
        old=datetime(2026,9,30,23,tzinfo=ZoneInfo('America/Fortaleza')).timestamp()
        with self.store.connect() as c:c.execute('UPDATE transcripts SET created=?',(old,))
        publish(self.store,iid)
        with self.store.connect() as c:c.execute('UPDATE transcripts SET created=? WHERE current=1',(now,))
        other=register_channel(self.store,'https://youtube.com/@second','Outro');self.store.ingest(other,[{'id':A}])
        counts=summary(self.store,'America/Fortaleza',now)
        self.assertEqual(counts['transcripts'],{'total':1,'week':0,'month':0})
        with self.store.connect() as c:c.execute('UPDATE transcripts SET created=?',(now,))
        self.assertEqual(summary(self.store,'America/Fortaleza',now)['transcripts'],{'total':1,'week':1,'month':1})
        self.assertEqual(summary(self.store,'invalid/zone',now)['timezone'],'UTC')
    def test_known_items_start_before_discovery_finishes_and_only_once(self):
        s=self.source();self.store.ingest(s['id'],[{'id':A,'title':'Título'}]);start(self.store,s['id']);advance(self.store);advance(self.store)
        with self.store.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE kind='transcribe'").fetchone()[0],1)
            self.assertEqual(c.execute('SELECT state FROM channel_sessions').fetchone()[0],'discovering')
            self.assertEqual(c.execute('SELECT count(*) FROM session_items').fetchone()[0],1)
    def test_media_summary_counts_formats_once_and_uses_first_completion(self):
        import json
        from memoria.core import atomic_json,hash_file
        from memoria.statistics import completed_at
        s=self.source();self.store.ingest(s['id'],[{'id':A}]);iid='youtube_'+A
        file=self.store.root/'originals'/'fixture.mp4';file.write_bytes(b'controlled video');digest=hash_file(file)
        with self.store.connect() as c:
            c.execute('UPDATE items SET path=?,blob_hash=? WHERE id=?',(str(file.relative_to(self.store.root)),digest,iid))
            c.execute('INSERT INTO service_state VALUES(?,?)',('mp3:'+iid,json.dumps({'path':str(file.relative_to(self.store.root)),'sha256':digest,'collected_at':100})))
        (self.store.root/'metadata'/'assets'/iid).mkdir(parents=True)
        atomic_json(self.store.root/'metadata'/'assets'/iid/'video-fixture.json',{'collected_at':100})
        one=completed_at(self.store,iid,'video');self.assertEqual(completed_at(self.store,iid,'video'),one)
        self.assertEqual(summary(self.store,now=200)['media'],{'total':2,'week':2,'month':2})
    def test_pending_iterator_is_committed_only_after_durable_consumption(self):
        import sys
        from memoria.sync import SyncEngine
        from memoria.worker import Worker
        w=Worker(self.store,reserve=0);s=self.source()
        with self.store.connect() as c:self.store.enqueue(c,'sync',s['id'])
        job=self.store.claim(w.owner,kinds=('sync',));checkpoint=self.store.root/'temporary'/'iterator.xz';checkpoint.write_text('old')
        script="import sys,pathlib,json;p=pathlib.Path(sys.argv[2]);p.with_name(p.name+'.pending.xz').write_text('new');print(json.dumps({'id':'entry'}),flush=True)"
        command=[sys.executable,'-c',script,'--checkpoint',str(checkpoint)]
        def interrupted(_):raise RuntimeError('database interrupted')
        with self.assertRaises(RuntimeError):SyncEngine(w).stream(command,job,interrupted)
        self.assertEqual(checkpoint.read_text(),'old')
        seen=[];SyncEngine(w).stream(command,job,seen.append)
        self.assertEqual(checkpoint.read_text(),'new');self.assertEqual(seen,[{'id':'entry'}])
    def test_temporary_audio_and_discovery_do_not_inflate_summary(self):
        s=self.source();self.store.ingest(s['id'],[{'id':A}]);start(self.store,s['id']);advance(self.store)
        self.assertEqual(summary(self.store)['transcripts']['total'],0);self.assertEqual(summary(self.store)['media']['total'],0)

if __name__=='__main__':unittest.main()
