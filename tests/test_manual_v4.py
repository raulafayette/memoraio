import json
from pathlib import Path
import tempfile
import unittest
from memoria.core import Store,atomic_json,hash_file
from memoria.inventory import assets,inventory
from memoria.library import publish_library
from memoria.operations import request


def seed(store):
    sid=store.register_source('https://youtu.be/BaW_jenozKc')
    store.ingest(sid,[{'id':'BaW_jenozKc','title':'Texto pronto'},{'id':'abcdefghijk','title':'Conteúdo pendente'}])
    iid='youtube_BaW_jenozKc';p=store.root/'transcripts'/iid/'t'/'transcript.json'
    p.parent.mkdir(parents=True)
    atomic_json(p,{'id':'t','segments':[{'start':0,'end':2,'text':'Fala integral para abrir com um clique.'}],'origin':'manual_caption','duration':2})
    with store.connect() as c:c.execute('INSERT INTO transcripts VALUES(?,?,?,?,?,?,?,?,?,?,1)',('t',iid,1790000000,'manual_caption','pt','null',str(p.relative_to(store.root)),hash_file(p),'structural_pass','{}'))
    publish_library(store,iid)
    return iid

class ManualInventory(unittest.TestCase):
    def test_manual_defaults_and_no_scheduled_work(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);seed(s)
            with s.connect() as c:
                source=c.execute('SELECT * FROM sources').fetchone()
                self.assertEqual(source['cadence'],'manual');self.assertEqual(source['auto_process'],0)
                self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
            self.assertEqual(s.tick(),[])
    def test_ready_requires_real_file_and_detects_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);seed(s);one=inventory(s,{})
            self.assertEqual(one['counts']['ready'],1);self.assertEqual(one['counts']['pending'],1)
            Path(one['items'][0]['assets']['txt']['path']).write_text('alterado')
            self.assertEqual(inventory(s,{})['counts']['ready'],0)
    def test_missing_video_is_never_skipped_and_mp3_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);iid=seed(s);p=s.root/'originals'/'test.mp3';p.write_bytes(b'controlled audio checksum fixture')
            with s.connect() as c:
                c.execute("UPDATE items SET path='originals/absent.mp4',blob_hash='missing',status='archived' WHERE id=?",(iid,))
                c.execute('INSERT INTO service_state VALUES(?,?)',('mp3:'+iid,json.dumps({'path':str(p.relative_to(s.root)),'sha256':hash_file(p)})))
                item=c.execute('SELECT * FROM items WHERE id=?',(iid,)).fetchone();self.assertNotIn('video',assets(s,c,item))
            self.assertEqual(request(s,[iid],['audio'],{'audio_format':'mp3'}),[])
            self.assertEqual(len(request(s,[iid],['video'])),1)
            p.write_bytes(b'changed')
            self.assertEqual(len(request(s,[iid],['audio'],{'audio_format':'mp3'})),1)
    def test_manual_mode_survives_restart_even_with_legacy_due_source(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);s.register_source('https://youtube.com/@fixture',cadence='monthly')
            with s.connect() as c:c.execute("INSERT INTO service_state VALUES('manual_mode','1')")
            self.assertEqual(Store(d).tick(),[])

class StandardVideo(unittest.TestCase):
    def test_webm_is_converted_to_mp4_h264_aac_and_not_requeued(self):
        import shutil,subprocess
        from memoria.worker import Worker
        if not shutil.which('ffmpeg'):self.skipTest('FFmpeg necessário')
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);iid=seed(s);request(s,[iid],['video']);w=Worker(s,reserve=0);job=s.claim(w.owner,kinds=('download',))
            stage=s.root/'temporary'/iid;stage.mkdir(exist_ok=True);fixture=stage/'media.webm'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=64x64:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libvpx-vp9','-c:a','libopus','-shortest',str(fixture)],check=True)
            real=w.run_command
            def run(args,j):
                if '--print' in args:return str(fixture)
                if '--version' in args:return 'controlled-fixture'
                return real(args,j)
            w.run_command=run;w.download(job);s.finish(job,w.owner)
            with s.connect() as c:item=c.execute('SELECT * FROM items WHERE id=?',(iid,)).fetchone()
            target=s.root/item['path'];self.assertEqual(target.suffix,'.mp4')
            streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(target)]))['streams']
            self.assertEqual({x['codec_name'] for x in streams},{'h264','aac'})
            self.assertFalse(fixture.exists());self.assertEqual(request(s,[iid],['video']),[])

class CaptionOnly(unittest.TestCase):
    def test_instagram_never_acquires_media_in_caption_mode(self):
        from unittest.mock import patch
        from memoria.worker import Worker
        from memoria.transcription import Transcriber
        from memoria.core import Failure
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);iid=seed(s)
            with s.connect() as c:c.execute("UPDATE items SET platform='instagram' WHERE id=?",(iid,))
            request(s,[iid],['transcript'],{'only_missing':False});w=Worker(s,reserve=0);job=s.claim(w.owner,kinds=('transcribe',))
            with patch.object(w,'run_command') as network,patch.object(Transcriber,'audio') as audio:
                with self.assertRaises(Failure):Transcriber(w).run(job)
                network.assert_not_called();audio.assert_not_called()
    def test_youtube_without_captions_never_falls_back_to_audio(self):
        from unittest.mock import patch
        from memoria.worker import Worker
        from memoria.transcription import Transcriber
        from memoria.core import Failure
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);iid=seed(s);request(s,[iid],['transcript'],{'only_missing':False})
            w=Worker(s,reserve=0);job=s.claim(w.owner,kinds=('transcribe',))
            with patch.object(w,'run_command',side_effect=[json.dumps({'id':'BaW_jenozKc'}),Failure('Sem legenda','failed')]),patch.object(Transcriber,'captions',return_value=None),patch.object(Transcriber,'audio') as audio:
                with self.assertRaises(Failure):Transcriber(w).run(job)
                audio.assert_not_called()

class ManualTransition(unittest.TestCase):
    def test_migration_cancels_legacy_jobs_but_preserves_manual_batch_and_files(self):
        from memoria.manual import enable
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);iid=seed(s)
            with s.connect() as c:legacy=s.enqueue(c,'transcribe','youtube_abcdefghijk');c.execute("UPDATE sources SET cadence='monthly',auto_process=1,next_sync=1")
            explicit=request(s,[iid],['video'])[0]
            self.assertTrue(enable(s));self.assertFalse(enable(s))
            with s.connect() as c:
                self.assertEqual(c.execute('SELECT state FROM jobs WHERE id=?',(legacy,)).fetchone()[0],'cancelled')
                self.assertEqual(c.execute('SELECT state FROM jobs WHERE id=?',(explicit,)).fetchone()[0],'queued')
            self.assertEqual(inventory(s,{})['counts']['ready'],1);self.assertEqual(s.tick(),[])
